"""Transporte HTTP de pares conserva identidades y snapshot, sin modelos."""

from datetime import datetime, timezone
from dataclasses import replace
import json
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from operix_engine.event_publishing import EventContext, HttpEventSink, event_candidate_payload
from operix_engine.rules import PairEventCandidate, InteractionIdentity
from operix_engine.spatiotemporal import ObjectIdentity
from operix_engine.proximity_geometry import PROXIMITY_GEOMETRY_VERSION
from operix_engine.zone_geometry import NormalizedPoint


class PairPublishingTests(unittest.TestCase):
    def setUp(self):
        self.pair = PairEventCandidate("TEST_DATA_PAIR", 1, 60, 2.,
            InteractionIdentity(ObjectIdentity("person", 1), ObjectIdentity("forklift", 1)),
            "TEST_DATA_ZONE", {"kind": "person_forklift_proximity", "zone_id": "TEST_DATA_ZONE",
            "person_class": "person", "forklift_class": "forklift", "max_distance": .25,
            "minimum_duration_seconds": 1.}, 30, 1., .2, 1.)
        self.context = EventContext(uuid4(), "TEST_DATA_VIEW", datetime.now(timezone.utc),
                                    {"kind": "controlled_fixture"})

    def test_pair_has_no_fictitious_single_track_and_preserves_raw_observations(self):
        body = event_candidate_payload(self.pair, self.context)
        self.assertNotIn("track_id", body)
        self.assertEqual(body["interaction"]["person"]["track_id"], 1)
        self.assertEqual(body["interaction"]["forklift"]["track_id"], 1)
        self.assertEqual(body["observations"], {"normalized_distance": .2, "duration_s": 1.})
        self.assertEqual(body["episode"]["started_timestamp_s"], 1.)
        self.assertEqual(body["source"]["kind"], "controlled_fixture")

    def test_versioned_geometry_reaches_event_without_changing_legacy_payload(self):
        candidate = replace(self.pair, proximity_geometry_version=PROXIMITY_GEOMETRY_VERSION,
                            person_anchor=NormalizedPoint(.2,.5), equipment_target=NormalizedPoint(.4,.5))
        observed = event_candidate_payload(candidate, self.context)["observations"]
        self.assertEqual(observed["normalized_distance"], .2)
        self.assertEqual(observed["proximity_geometry"], candidate.proximity_geometry)
        self.assertNotIn("proximity_geometry", event_candidate_payload(self.pair, self.context)["observations"])

    def test_sink_deduplicates_pair_but_not_other_pair_or_episode(self):
        response = MagicMock()
        response.__enter__.return_value.status = 201
        response.__enter__.return_value.read.return_value = json.dumps({"id": str(uuid4())}).encode()
        sink = HttpEventSink("http://127.0.0.1:8000/api/v1")
        other = replace(self.pair, interaction=InteractionIdentity(ObjectIdentity("person", 1), ObjectIdentity("forklift", 2)))
        episode = replace(self.pair, frame_index=120, timestamp_s=4., started_frame_index=90, started_timestamp_s=3.)
        with patch("operix_engine.event_publishing.urlopen", return_value=response) as send:
            self.assertEqual(sink.publish(self.pair, self.context).status, "published")
            self.assertEqual(sink.publish(self.pair, self.context).status, "duplicate")
            self.assertEqual(sink.publish(other, self.context).status, "published")
            self.assertEqual(sink.publish(episode, self.context).status, "published")
        self.assertEqual(send.call_count, 3)

    def test_local_cache_does_not_mask_incompatible_observations(self):
        from urllib.error import HTTPError
        response = MagicMock()
        response.__enter__.return_value.status = 201
        identity = str(uuid4())
        response.__enter__.return_value.read.return_value = json.dumps({"id": identity}).encode()
        sink = HttpEventSink("http://127.0.0.1:8000/api/v1")
        with patch("operix_engine.event_publishing.urlopen", side_effect=[response, HTTPError("local",409,"conflict",{},None)]) as send:
            self.assertEqual(sink.publish(self.pair,self.context).status,"published")
            self.assertEqual(sink.publish(self.pair,self.context).event_id, identity)
            self.assertEqual(sink.publish(replace(self.pair,observed_normalized_distance=.1),self.context).http_status,409)
        self.assertEqual(send.call_count,2)
