"""Worker desacoplado. En Compose: docker compose up --scale worker=4."""
import logging
import signal
import time
from .db import initialize
from .jobs import claim_job, execute_job
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
RUNNING = True

def shutdown(*args):
    global RUNNING
    RUNNING = False

def main():
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    initialize()
    logging.info('Worker NORECOV iniciado')
    while RUNNING:
        try:
            job = claim_job()
            if job:
                logging.info('Ejecutando trabajo %s (%s)', job['_id'], job['kind'])
                execute_job(job)
            else:
                time.sleep(2)
        except Exception:
            logging.exception('Error en la cola')
            time.sleep(5)

if __name__ == '__main__':
    main()
