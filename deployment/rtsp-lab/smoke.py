"""GPU-dependent smoke for the two licensed lab streams. It persists lab events."""
import argparse
from pathlib import Path
from time import monotonic, sleep
import hashlib, json, os, subprocess
from urllib.parse import urlsplit
import requests

arguments = argparse.ArgumentParser(description=__doc__)
arguments.add_argument("--output", required=True, type=Path)
arguments.add_argument("--base-url", default="http://127.0.0.1:13000")
arguments.add_argument("--project", default="operix")
arguments.add_argument("--env-file", default="../Operix-Docker/operix.env")
arguments.add_argument("--shared", action="store_true", help="Require the shared inference profile")
args = arguments.parse_args()
origin = urlsplit(args.base_url)
if (origin.scheme != "http" or origin.hostname != "127.0.0.1" or origin.netloc != f"127.0.0.1:{origin.port}"
        or origin.path or origin.query or origin.fragment):
    arguments.error("--base-url must be a local 127.0.0.1 origin with an explicit port")
root = args.output.resolve()
root.mkdir(parents=True, exist_ok=False)
os.chdir(Path(__file__).resolve().parents[2])
base=args.base_url
api="/api/v1"
camera_api=f"{api}/analysis/cameras/"
ids=["lab-cam-01","lab-cam-02"]
compose=["docker","compose","--env-file",args.env_file,"-p",args.project,"-f","compose.yaml","-f","compose.gpu.yaml","-f","compose.rtsp-lab.yaml"]
if args.shared:
    compose += ["-f", "compose.rtsp-inference.yaml"]

def request(client, method, path, code=200, **options):
    response=client.request(method,base+path,timeout=30,**options)
    assert response.status_code==code,(method,path,response.status_code)
    return response

def login(role):
    client=requests.Session()
    info=request(client,"GET",f"{api}/auth/session/").json()
    role_key = role.upper()
    data = {
        "username": os.environ[f"OPERIX_LAB_TEST_{role_key}_USER"],
        "password": os.environ[f"OPERIX_LAB_TEST_{role_key}_PASSWORD"],
    }
    response=request(client,"POST",f"{api}/auth/login/",headers={"X-CSRFToken":info["csrf_token"],"Origin":base},json=data).json()
    assert response["user"]["role"]==role
    client.headers.update({"Origin":base,"X-CSRFToken":response["csrf_token"]})
    return client

def wait(fn,label,timeout=105):
    end=monotonic()+timeout
    while monotonic()<end:
        value=fn()
        if value is not None and value is not False:
            return value
        sleep(.75)
    raise TimeoutError(label)

admin=login("administrator")
safety=login("safety_lead")
viewer=login("viewer")
anon=requests.Session()
request(anon,"GET",camera_api,401)
request(viewer,"GET",camera_api,403)
request(viewer,"POST",camera_api+ids[0]+"/stop/",403,json={})
cameras=request(admin,"GET",camera_api).json()
assert cameras["enabled"] and len(cameras["cameras"])==2
camera=lambda ident:request(admin,"GET",camera_api+ident+"/").json()
events=lambda ident:request(admin,"GET",f"{api}/events/?camera_id={ident}").json()
def publish_control(action,id_):
    subprocess.run([*compose,action,id_],check=True,capture_output=True)
receipt={"solo":{}, "dual":{}, "interruption":{}, "events":{}}
runs={}
publisher_interrupted = False
assert all(camera["status"] in {"stopped", "error"} for camera in cameras["cameras"])
try:
    for item in cameras["cameras"]:
        ident=item["id"]
        assert item["provenance"]["real"] is True and item["provenance"]["license"]=="CC BY 4.0"
        assert "rtsp://" not in json.dumps(item)
        document=item["configuration"]
        # Real footage is a laboratory input. Each camera retains its own versioned rules.
        if item["revision"]==0:
            document["zones"][0]["name"]="Encuadre de "+ident
            request(admin,"PUT",camera_api+ident+"/",json={"revision":item["revision"],"document":document})
    def start(ident):
        data=request(admin,"POST",camera_api+ident+"/start/",202,json={}).json()
        runs[ident]=data["run_id"]
        print("start",ident,runs[ident],flush=True)
    def processed(ident,minimum):
        data=camera(ident)
        if data["status"]=="error":
            raise RuntimeError((ident,data))
        return data if data["metrics"].get("frames_processed",0)>=minimum else None
    start(ids[0])
    receipt["solo"][ids[0]]=wait(lambda:processed(ids[0],36),"Primera cámara sin suficientes frames")
    start(ids[1])
    wait(lambda:processed(ids[1],36),"Segunda cámara sin suficientes frames")
    for ident in ids:
        data=camera(ident)
        assert data["preview_url"]
        if args.shared:
            assert data["metrics"]["inference_mode"] == "shared"
            assert sum(data["metrics"]["inference_batch_sizes"].values()) > 0
        receipt["dual"][ident]=data
        preview=request(safety,"GET",data["preview_url"])
        request(anon,"GET",data["preview_url"],401)
        assert preview.content.startswith(b"\xff\xd8")
        (root/(ident+"-preview.jpg")).write_bytes(preview.content)
    second_before=camera(ids[1])["metrics"]["frames_processed"]
    first_before=camera(ids[0])["metrics"]["frames_processed"]
    publish_control("stop","lab-publisher-01")
    publisher_interrupted = True
    receipt["interruption"]["down"]=wait(lambda:(value if (value:=camera(ids[0]))["status"] in {"no_signal","reconnecting"} else None),"Señal perdida no reflejada")
    receipt["interruption"]["other"]=wait(lambda:processed(ids[1],second_before+12),"Cámara sana no avanzó")
    publish_control("start","lab-publisher-01")
    publisher_interrupted = False
    receipt["interruption"]["recovered"]=wait(lambda:processed(ids[0],first_before+12),"Primera cámara no reconectó")
    for ident in ids:
        candidates=events(ident)
        if isinstance(candidates,dict):
            candidates=candidates["results"]
        candidates=[entry for entry in candidates if str(entry["analysis_run_id"])==runs[ident]]
        assert candidates,(ident, "sin eventos")
        event=request(admin,"GET",f"{api}/events/{candidates[0]['id']}/").json()
        assert event["source"]["camera_id"]==ident
        assert event["source"]["timestamp_basis"]=="LAB_RECEPTION_UTC"
        assert event["source"]["capture"]["received_at"] and event["source"]["capture"]["processed_at"]
        if args.shared:
            for role, model_id in (("person", "YOLO11M_COCO_PERSON"), ("forklift", "FORKLIFT_SPECIALIST_V2")):
                model = event["source"]["perception"][role]
                assert model["model_id"] == model_id
                assert model["weights_sha256"] == event["source"][f"{role}_weights_sha256"]
        if not event["evidence_clip"]:
            event=wait(lambda:(e if (e:=request(admin,"GET",f"{api}/events/{candidates[0]['id']}/").json())["evidence_clip"] else None),"sin clip")
        for suffix,url in [("png",event["evidence_url"]),("mp4",event["evidence_clip"]["url"])]:
            assert url
            request(anon,"GET",url,401)
            request(viewer,"GET",url,403)
            binary=request(safety,"GET",url).content
            if suffix=="mp4":
                assert hashlib.sha256(binary).hexdigest()==event["evidence_clip"]["sha256"]
            else:
                assert binary.startswith(b"\x89PNG")
            (root/(ident+"-event."+suffix)).write_bytes(binary)
        receipt["events"][ident]=event
        print("event",ident,event["id"],event["frame_index"],flush=True)
    default_history=request(admin,"GET",f"{api}/events/").json()
    records=default_history.get("results",[]) if isinstance(default_history,dict) else default_history
    assert all(value.get("source",{}).get("kind")!="lab" for value in records)
finally:
    if publisher_interrupted:
        subprocess.run([*compose,"start","lab-publisher-01"],capture_output=True,timeout=30)
    for ident in runs:
        request(admin,"POST",camera_api+ident+"/stop/",202,json={})
    for ident in runs:
        receipt.setdefault("stopped",{})[ident]=wait(lambda:(v if (v:=camera(ident))["status"]=="stopped" else None),"Cámara no se detuvo")
    (root/"receipt.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding="utf-8")
print("RTSP lab E2E en ambas cámaras, caída aislada, reconexión, permisos y detención",flush=True)
