"""Persistencia de observaciones del Motor, sin cálculo de movimiento en API."""
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APITestCase
from config.test_clients import administrator_client
from .test_pair_events import pair_payload


def motion_payload():
    data=pair_payload()
    data["rule_parameters"]["motion_condition"]="moving"
    data["source"]["epoch"]=3
    data["observations"]["equipment_motion"]={
        "version":"bottom_center_window_motion_v1","state":"MOVING","speed":.1,
        "unit":"normalized_image_per_s","frame_index":60,"timestamp_s":2.,"epoch":3,
        "start_timestamp_s":1.,"duration_s":1.,"sample_count":31,"position_residual":.001,
        "reason":None,"calibration_sha256":None,"configuration":{
            "unit":"normalized","window_seconds":1.,"min_observations":3,"max_gap_seconds":.2,
            "stationary_speed":.01,"moving_speed":.05,"max_position_residual":.01,"camera_fixed_confirmed":True}}
    return data

@override_settings(EVENT_POST_ENABLED=True)
class MotionEventTests(APITestCase):
    def setUp(self):
        self.client=administrator_client()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.OPERIX_EVENT_PUBLISH_TOKEN}")

    def post(self,data):
        return self.client.post("/api/v1/events/",data,format="json")

    def test_authorized_snapshot_round_trip_and_same_numeric_ids(self):
        data=motion_payload()
        response=self.post(data)
        self.assertEqual(response.status_code,201,response.data)
        event=self.client.get(f"/api/v1/events/{response.data['id']}/").data
        for field in ("observations","interaction","source","rule_parameters"):
            self.assertEqual(event[field],data[field])
        self.assertEqual(self.post(data).status_code,200)

    def test_rejects_missing_unknown_stationary_or_mismatched_frame_epoch(self):
        for changes in ({"state":"UNKNOWN","reason":"insufficient_observations"},{"state":"STATIONARY"},
                        {"frame_index":61},{"epoch":2},{"unit":"m_per_s"},{"duration_s":0},
                        {"speed":.001},{"position_residual":.1}):
            data=motion_payload()
            data["observations"]["equipment_motion"].update(changes)
            response=self.post(data)
            self.assertEqual(response.status_code,400,response.data)
        data=motion_payload();data["observations"].pop("equipment_motion")
        self.assertEqual(self.post(data).status_code,400)

    def test_historical_optional_and_stationary_any_mode(self):
        self.assertEqual(self.post(pair_payload()).status_code,201)
        data=motion_payload();data["rule_parameters"]["motion_condition"]="any"
        data["observations"]["equipment_motion"].update(state="STATIONARY",speed=0)
        self.assertEqual(self.post(data).status_code,201)

    def test_unknown_types_are_400_not_500_and_metric_requires_provenance(self):
        for changes in ({"state":[]},{"unit":[]},{"configuration":None},{"speed":True}):
            data=motion_payload();data["observations"]["equipment_motion"].update(changes)
            self.assertEqual(self.post(data).status_code,400)
        data=motion_payload();m=data["observations"]["equipment_motion"]
        m["unit"]="m_per_s";m["configuration"]["unit"]="m"
        self.assertEqual(self.post(data).status_code,400)

    def test_new_epoch_reuses_tracks_without_colliding_with_previous_event(self):
        data=motion_payload()
        first=self.post(data)
        self.assertEqual(first.status_code,201)
        data["source"]["epoch"]=4
        data["observations"]["equipment_motion"]["epoch"]=4
        second=self.post(data)
        self.assertEqual(second.status_code,201,second.data)
        self.assertNotEqual(first.data["id"],second.data["id"])
        self.assertEqual(self.post(data).status_code,200)

    def test_metric_motion_requires_an_unchanged_calibration_snapshot(self):
        import hashlib
        import json
        data=motion_payload()
        cal={"status":"valid","source_sha256":"a"*64,"version":1,"units":"m",
             "method":"ground_plane_contact_edges_v1","image_points":[[0,0],[1,0],[1,1],[0,1]],
             "ground_points_m":[[0,0],[10,0],[10,10],[0,10]],"homography":[[10,0,0],[0,10,0],[0,0,1]]}
        cal["sha256"]=hashlib.sha256(json.dumps(cal,sort_keys=True,allow_nan=False).encode()).hexdigest()
        m=data["observations"]["equipment_motion"]
        m.update(unit="m_per_s",calibration_sha256=cal["sha256"])
        m["configuration"]["unit"]="m"
        data["source"].update(video_sha256="a"*64,spatial_configuration={"calibration":cal,"motion":m["configuration"]})
        response=self.post(data)
        self.assertEqual(response.status_code,201,response.data)
        cal["version"]=2
        self.assertEqual(self.post(data).status_code,400)
        data["source"]["spatial_configuration"]["calibration"]=None
        self.assertEqual(self.post(data).status_code,400)
