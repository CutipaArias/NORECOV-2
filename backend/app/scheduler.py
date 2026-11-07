"""APScheduler: lee planes persistidos en MongoDB y encola trabajos."""
import logging
import signal
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from bson import ObjectId
from .db import db, initialize, audit, utcnow
from .jobs import enqueue, do_retention

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
ACTIVE = True

def queue_plan(plan_id):
    plan = db().planes_backup.find_one({'_id':ObjectId(plan_id),'active':True})
    if plan:
        enqueue('backup', plan['node_id'], actor='scheduler', plan_id=plan_id)

def sync_plans(scheduler):
    active_ids = set()
    for plan in db().planes_backup.find({'active':True}):
        name = f"plan:{plan['_id']}"
        try:
            trigger = CronTrigger.from_crontab(plan['cron'], timezone='UTC')
            existing = scheduler.get_job(name)
            if not existing or str(existing.trigger) != str(trigger):
                scheduler.add_job(queue_plan, trigger=trigger, id=name, replace_existing=True,
                    args=[str(plan['_id'])], coalesce=True, max_instances=1, misfire_grace_time=120)
            active_ids.add(name)
        except Exception as exc:
            audit('scheduler.plan_invalid', detail={'plan_id':str(plan['_id']),'error':str(exc)})
    for task in scheduler.get_jobs():
        if task.id.startswith('plan:') and task.id not in active_ids:
            scheduler.remove_job(task.id)

def prune_daily():
    result = do_retention()
    logging.info('Retención: %s', result)

def recover_abandoned():
    from datetime import timedelta
    from .db import utcnow
    cutoff = utcnow() - timedelta(minutes=45)
    result = db().jobs.update_many({'status':'running','updated_at':{'$lt':cutoff}},
        {'$set':{'status':'queued','progress':'Recuperado tras interrupción'}})
    if result.modified_count:
        audit('scheduler.requeued_jobs', detail={'count':result.modified_count})

def shutdown(*args):
    global ACTIVE
    ACTIVE = False

def main():
    global ACTIVE
    initialize()
    scheduler = BackgroundScheduler(timezone='UTC')
    scheduler.add_job(prune_daily, CronTrigger(hour=2, minute=15, timezone='UTC'), id='retention')
    scheduler.add_job(recover_abandoned,'interval', minutes=5, id='requeue')
    scheduler.add_job(sync_plans, 'interval', seconds=30, id='sync', args=[scheduler])
    scheduler.start()
    sync_plans(scheduler)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    logging.info('Scheduler NORECOV activo (zona UTC)')
    while ACTIVE:
        time.sleep(1)
    scheduler.shutdown(wait=False)

if __name__ == '__main__':
    main()
