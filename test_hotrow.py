import time, os, uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from daily_agent.config import Settings
from daily_agent.models import UsageWindow
from daily_agent.services import reserve_budget, ensure_usage_window
from tests.conftest import create_identity

def test():
    db_url = "postgresql+psycopg://daily_agent_test:daily_agent_test@127.0.0.1:55433/daily_agent_test"
    engine = create_engine(db_url, pool_pre_ping=True, pool_size=150, max_overflow=50)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(environment="test", database_url=db_url, auth_secret="sec", webhook_secret="sec", global_daily_budget_micro=100000000)
    
    with factory() as session:
        account, user, token = create_identity(session, settings, name="LoadTest3")
        ensure_usage_window(session, account.id, settings)
        window = session.query(UsageWindow).filter_by(account_id=account.id).first()
        window.everyday_limit = 100000
        window.spend_limit_micro = 10000000
        session.commit()

    def worker(i):
        with factory() as session:
            try:
                reserve_budget(session, settings=settings, account_id=account.id, logical_request_id=f"req3-{uuid.uuid4()}", stage="exec", amount_micro=1)
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                return False

    for concurrency in [10, 25, 50, 100]:
        tasks = concurrency * 5
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(worker, range(tasks)))
        duration = time.time() - t0
        print(f"Concurrency {concurrency}: {sum(results)} successes out of {tasks} in {duration:.2f}s ({sum(results)/duration:.2f} req/s)")

if __name__ == '__main__':
    test()
