"""Comprueba trazabilidad del movimiento recibido; no estima velocidades."""
import math
import hashlib
import json
from rest_framework.exceptions import ValidationError


def validate_motion(attrs):
    parameters = attrs["rule_parameters"]
    motion = attrs.get("observations",{}).get("equipment_motion")
    if motion is None:
        if parameters.get("motion_condition") == "moving":
            raise ValidationError("La regla requiere movimiento observado")
        return
    expected = {"version","state","speed","unit","frame_index","timestamp_s","epoch",
                "start_timestamp_s","duration_s","sample_count","position_residual","reason",
                "configuration","calibration_sha256"}
    if not isinstance(motion,dict) or set(motion) != expected:
        raise ValidationError("Snapshot de movimiento incompleto")
    if motion["version"] != "bottom_center_window_motion_v1" or (not isinstance(motion["state"],str) or motion["state"] not in {"MOVING","STATIONARY","UNKNOWN"}):
        raise ValidationError("Versión o estado de movimiento no soportado")
    cfg=motion["configuration"]
    keys={"unit","window_seconds","min_observations","max_gap_seconds","stationary_speed",
          "moving_speed","max_position_residual","camera_fixed_confirmed"}
    if not isinstance(cfg,dict) or set(cfg)!=keys or type(cfg["camera_fixed_confirmed"]) is not bool:
        raise ValidationError("Configuración de movimiento incompleta")
    def number(value):
        try:
            valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValidationError("Movimiento requiere números finitos no negativos")
        return value
    for key in keys-{"unit","camera_fixed_confirmed","min_observations"}:number(cfg[key])
    if ((not isinstance(cfg["unit"],str) or cfg["unit"] not in {"normalized","m"}) or not 0<cfg["max_gap_seconds"]<=cfg["window_seconds"]<=30
            or type(cfg["min_observations"]) is not int or not 3<=cfg["min_observations"]<=4096
            or cfg["stationary_speed"]>=cfg["moving_speed"]):
        raise ValidationError("Parámetros de movimiento incompatibles")
    if motion["unit"] != ("m_per_s" if cfg["unit"]=="m" else "normalized_image_per_s"):
        raise ValidationError("Unidad de movimiento incompatible")
    if (type(motion["frame_index"]) is not int or motion["frame_index"]!=attrs["frame_index"]
            or type(motion["epoch"]) is not int or motion["epoch"]<0
            or motion["epoch"]!=attrs.get("source",{}).get("epoch",0)
            or abs(number(motion["timestamp_s"])-float(attrs["video_timestamp_s"]))>.000500001
            or type(motion["sample_count"]) is not int or not 0<=motion["sample_count"]<=4096):
        raise ValidationError("Movimiento de otro frame o época")
    duration=number(motion["duration_s"])
    if motion["start_timestamp_s"] is not None:
        if abs(motion["timestamp_s"]-number(motion["start_timestamp_s"])-duration)>1e-9:
            raise ValidationError("Ventana temporal incompatible")
    elif duration or motion["sample_count"]:
        raise ValidationError("Ventana temporal incompleta")
    if motion["position_residual"] is not None:number(motion["position_residual"])
    if motion["speed"] is not None:number(motion["speed"])
    if motion["state"] != "UNKNOWN":
        if (not cfg["camera_fixed_confirmed"] or motion["speed"] is None
                or motion["position_residual"] is None or motion["position_residual"]>cfg["max_position_residual"]+1e-12
                or duration<cfg["window_seconds"]-1e-9 or motion["sample_count"]<cfg["min_observations"]):
            raise ValidationError("Movimiento sin observaciones suficientes o referencia fija")
        if motion["state"]=="MOVING" and motion["speed"]<cfg["moving_speed"] and not math.isclose(motion["speed"], cfg["moving_speed"], rel_tol=1e-12, abs_tol=0):
            raise ValidationError("Movimiento no alcanza el parámetro registrado")
        if motion["state"]=="STATIONARY" and motion["speed"]>cfg["stationary_speed"] and not math.isclose(motion["speed"], cfg["stationary_speed"], rel_tol=1e-12, abs_tol=0):
            raise ValidationError("Estado estacionario incompatible")
    elif not isinstance(motion["reason"],str) or not motion["reason"]:
        raise ValidationError("Movimiento indeterminado requiere motivo")
    source=attrs.get("source",{}).get("spatial_configuration",{})
    if source.get("motion") is not None and source["motion"]!=cfg:
        raise ValidationError("Movimiento no corresponde a la configuración efectiva")
    if cfg["unit"]=="m" and motion["state"]!="UNKNOWN":
        cal=source.get("calibration",{})
        if not isinstance(cal, dict):
            raise ValidationError("La calibración de movimiento debe ser un snapshot")
        try:
            digest = hashlib.sha256(json.dumps({k:v for k,v in cal.items() if k != "sha256"}, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (TypeError, ValueError):
            raise ValidationError("Calibración de movimiento no serializable") from None
        if (cal.get("status")!="valid" or motion["calibration_sha256"]!=digest or cal.get("sha256")!=digest
                or not isinstance(cal.get("source_sha256"),str)
                or cal.get("source_sha256")!=attrs.get("source",{}).get("video_sha256")):
            raise ValidationError("Velocidad aproximada sin calibración trazable")
    if parameters.get("motion_condition")=="moving" and motion["state"]!="MOVING":
        raise ValidationError("La condición requiere movimiento observado")
