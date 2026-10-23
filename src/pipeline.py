"""Synthetic, offline veterinary dispatch ETL demo; not the live VetsKart backend."""
from __future__ import annotations
import argparse
import csv
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*r*math.asin(min(1.0,math.sqrt(a)))

def validate_requests(rows: list[dict[str,str]]) -> tuple[list[dict],list[dict]]:
    accepted, rejected, seen = [], [], set()
    for row in rows:
        try:
            request_id = row["request_id"].strip()
            if not request_id or request_id in seen:
                raise ValueError("missing or duplicate request_id")
            seen.add(request_id)
            lat, lon = float(row["latitude"]), float(row["longitude"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("invalid coordinates")
            service = row["service_type"].strip().lower()
            if not service:
                raise ValueError("missing service_type")
            when = datetime.fromisoformat(row["requested_at"].replace("Z","+00:00"))
            if when.tzinfo is None:
                raise ValueError("requested_at must include timezone")
            accepted.append({"request_id":request_id,"pet_name":row["pet_name"].strip(),
                "service_type":service,"latitude":lat,"longitude":lon,"requested_at":when.isoformat()})
        except (KeyError, ValueError, TypeError) as exc:
            rejected.append({"request_id":row.get("request_id",""),"reason":str(exc)})
    return accepted,rejected

def validate_vets(rows: list[dict[str,str]]) -> list[dict]:
    vets=[]
    for row in rows:
        try:
            lat,lon,radius=float(row["latitude"]),float(row["longitude"]),float(row["service_radius_km"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180 and radius > 0):
                continue
            vets.append({"vet_id":row["vet_id"],"name":row["name"],"latitude":lat,"longitude":lon,
                "service_radius_km":radius,"services":{x.strip().lower() for x in row["services"].split("|")},
                "available":row["available"].strip().lower()=="true"})
        except (KeyError,ValueError):
            continue
    return vets

def assign_requests(requests: list[dict], vets: list[dict]) -> list[dict]:
    """Closest eligible available vet, reserved at most once per batch."""
    assigned, reserved=[],set()
    for req in sorted(requests,key=lambda r:(r["requested_at"],r["request_id"])):
        candidates=[]
        for vet in vets:
            if not vet["available"] or vet["vet_id"] in reserved or req["service_type"] not in vet["services"]:
                continue
            distance=km_between(req["latitude"],req["longitude"],vet["latitude"],vet["longitude"])
            if distance<=vet["service_radius_km"]:
                candidates.append((distance,vet["vet_id"]))
        if candidates:
            distance,vet_id=min(candidates)
            reserved.add(vet_id)
            assigned.append({"request_id":req["request_id"],"vet_id":vet_id,
                "distance_km":round(distance,2),"status":"assigned"})
        else:
            assigned.append({"request_id":req["request_id"],"vet_id":None,
                "distance_km":None,"status":"unassigned"})
    return assigned

def save_database(path:Path, requests:list[dict], assignments:list[dict]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS service_requests (
          request_id TEXT PRIMARY KEY, pet_name TEXT NOT NULL, service_type TEXT NOT NULL,
          latitude REAL NOT NULL, longitude REAL NOT NULL, requested_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assignments (
          request_id TEXT PRIMARY KEY REFERENCES service_requests(request_id),
          vet_id TEXT, distance_km REAL, status TEXT NOT NULL);
        """)
        db.executemany("""INSERT INTO service_requests VALUES
          (:request_id,:pet_name,:service_type,:latitude,:longitude,:requested_at)
          ON CONFLICT(request_id) DO UPDATE SET
          pet_name=excluded.pet_name, service_type=excluded.service_type,
          latitude=excluded.latitude, longitude=excluded.longitude, requested_at=excluded.requested_at""",requests)
        db.executemany("""INSERT INTO assignments VALUES (:request_id,:vet_id,:distance_km,:status)
          ON CONFLICT(request_id) DO UPDATE SET vet_id=excluded.vet_id,
          distance_km=excluded.distance_km,status=excluded.status""",assignments)

def run(data_dir:Path,output_dir:Path)->dict:
    requests,rejected=validate_requests(read_csv(data_dir/"requests.csv"))
    vets=validate_vets(read_csv(data_dir/"veterinarians.csv"))
    assignments=assign_requests(requests,vets)
    output_dir.mkdir(parents=True,exist_ok=True)
    save_database(output_dir/"petcare.db",requests,assignments)
    with (output_dir/"assignments.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=["request_id","vet_id","distance_km","status"])
        writer.writeheader()
        writer.writerows(assignments)
    report={"requests_received":len(requests)+len(rejected),"valid_requests":len(requests),
        "invalid_requests":len(rejected),"assigned":sum(a["status"]=="assigned" for a in assignments),
        "unassigned":sum(a["status"]=="unassigned" for a in assignments),"rejected_records":rejected}
    (output_dir/"metrics.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="Run synthetic veterinary service dispatch ETL")
    parser.add_argument("--data-dir",type=Path,default=BASE/"data")
    parser.add_argument("--output-dir",type=Path,default=BASE/"output")
    args=parser.parse_args()
    print(json.dumps(run(args.data_dir,args.output_dir),indent=2))
