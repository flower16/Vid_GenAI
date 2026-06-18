"""Plan-comparison endpoints: kick off the LangGraph workflow and read results."""
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import SessionLocal, get_db
from app.agent.workflow import run_comparison
from app.api.files import resolve
from app.models import AuditLog, BillCalculation, ElectricityPlan, Job, User

router = APIRouter(prefix="/compare", tags=["compare"])

# Fast in-memory cache for live polling; SQLite `jobs` table is the durable record.
_JOBS: dict[str, dict] = {}


class IntakePayload(BaseModel):
    avg_monthly_usage_kwh: float
    monthly_export_kwh: float = 0
    monthly_self_consume_kwh: float = 0
    night_share: float = 0
    battery_installed: bool = False
    battery_kwh: float = 0
    ev_owned: bool = False
    solar_kw: float = 0
    current_provider: str | None = None
    current_annual_bill: float | None = None
    # Optional uploaded-file references (from POST /files/{kind})
    bill_file_id: str | None = None
    solar_file_id: str | None = None
    smt_file_id: str | None = None


def _persist_results(db: Session, job_id: str, user_id: int, result: dict):
    """Write one bill_calculations row per ranked plan + audit_logs for the run."""
    plan_by_name = {p.plan_name: p.id for p in db.query(ElectricityPlan).all()}
    for r in result.get("ranked", []):
        m = (r.get("monthly") or [{}])[0]
        db.add(BillCalculation(
            job_id=job_id, user_id=user_id,
            plan_id=plan_by_name.get(r.get("plan_name")),
            imported_cost=m.get("imported_energy_cost"),
            self_consumption_value=m.get("self_consumption_value"),
            export_credit=m.get("export_credit"),
            tdu_delivery_cost=m.get("tdu_delivery_cost"),
            base_fee=m.get("base_fee"), taxes_misc=m.get("taxes_misc"),
            est_monthly_bill=m.get("est_monthly_bill"),
            est_annual_bill=r.get("est_annual_bill"),
            annual_savings_vs_current=r.get("annual_savings_vs_current"),
            rank=r.get("rank"),
            assumptions_json=json.dumps(r.get("assumptions", [])),
        ))
    # Audit trail: each EFL citation used, plus a run-summary row.
    for c in result.get("citations", []):
        db.add(AuditLog(job_id=job_id, node="efl_rag_extract", tool="efl_lookup",
                        output_summary=f"cited {c.get('plan')}",
                        citations_json=json.dumps(c)))
    best = result.get("best_overall") or {}
    db.add(AuditLog(job_id=job_id, node="recommend", tool="rank_plans",
                    output_summary=f"best={best.get('provider')} "
                                   f"{best.get('plan_name')} "
                                   f"${best.get('est_annual_bill')}/yr",
                    citations_json=json.dumps(result.get("assumptions", []))))
    db.commit()


def _execute(job_id: str, user_id: int, intake: dict):
    _JOBS[job_id] = {"status": "running", "result": None}
    db = SessionLocal()
    try:
        job = db.query(Job).filter_by(job_id=job_id).first()
        if job:
            job.status = "running"
            db.commit()

        result = run_comparison(job_id, user_id, intake)

        _JOBS[job_id] = {"status": "complete", "result": result}
        if job:
            job.status = "complete"
            job.result_json = json.dumps(result, default=str)
            job.finished_at = datetime.utcnow()
            db.commit()
        _persist_results(db, job_id, user_id, result)
    except Exception as e:  # noqa: BLE001
        _JOBS[job_id] = {"status": "error", "result": {"error": str(e)}}
        db.rollback()
        job = db.query(Job).filter_by(job_id=job_id).first()
        if job:
            job.status = "error"
            job.result_json = json.dumps({"error": str(e)})
            job.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.post("")
def start_compare(payload: IntakePayload, background: BackgroundTasks,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    job_id = str(uuid.uuid4())
    intake = payload.model_dump()
    # Resolve uploaded file_ids -> server paths (ownership-checked) for the nodes.
    intake["bill_path"] = resolve(intake.pop("bill_file_id", None), db, user.id)
    intake["solar_path"] = resolve(intake.pop("solar_file_id", None), db, user.id)
    intake["smt_path"] = resolve(intake.pop("smt_file_id", None), db, user.id)

    db.add(Job(job_id=job_id, user_id=user.id, status="queued"))
    db.commit()

    _JOBS[job_id] = {"status": "queued", "result": None}
    background.add_task(_execute, job_id, user.id, intake)
    return {"job_id": job_id, "status": "queued"}


# NOTE: declared BEFORE /{job_id} so "history" isn't captured as a job_id.
@router.get("/history")
def history(user: User = Depends(get_current_user), limit: int = 50,
            db: Session = Depends(get_db)):
    """List the current user's past comparison runs, newest first."""
    rows = (db.query(Job)
            .filter(Job.user_id == user.id)
            .order_by(Job.created_at.desc()).limit(limit).all())
    out = []
    for j in rows:
        best = None
        if j.result_json:
            try:
                best = (json.loads(j.result_json) or {}).get("best_overall")
            except json.JSONDecodeError:
                best = None
        out.append({
            "job_id": j.job_id, "status": j.status,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "best_provider": (best or {}).get("provider"),
            "best_plan": (best or {}).get("plan_name"),
            "best_annual": (best or {}).get("est_annual_bill"),
        })
    return out


@router.get("/{job_id}")
def get_result(job_id: str, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    # Ownership check via the durable jobs table.
    job = db.query(Job).filter_by(job_id=job_id, user_id=user.id).first()
    if not job:
        return {"status": "not_found"}
    if job_id in _JOBS:                 # live cache for in-flight polling
        return _JOBS[job_id]
    return {"status": job.status,
            "result": json.loads(job.result_json) if job.result_json else None}
