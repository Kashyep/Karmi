from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from daily_agent.config import Settings
from daily_agent.models import PlatformBudget, UsageWindow, BudgetReservation, ReservationStatus
from daily_agent.services import reserve_budget, settle_budget
import os
from tests.conftest import create_identity

def test():
    db_url = "postgresql+psycopg://daily_agent_test:daily_agent_test@127.0.0.1:55433/daily_agent_test"
    os.environ["DAILY_AGENT_DATABASE_URL"] = db_url
    engine = create_engine(db_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(environment="test", database_url=db_url, auth_secret="sec", webhook_secret="sec", global_daily_budget_micro=50000)
    
    with factory() as session:
        account, user, token = create_identity(session, settings, name="Test Settler")
        reservation = reserve_budget(session, settings=settings, account_id=account.id, logical_request_id="test-req-1", stage="exec", amount_micro=10000)
        session.commit()
        res_id = reservation.id

    def settle(i):
        with factory() as session:
            try:
                res = session.get(BudgetReservation, res_id)
                settle_budget(session, res, attempt_id=f"test:{i}", actual_micro=1000)
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(settle, range(10)))

    with factory() as session:
        window = session.scalar(select(UsageWindow).where(UsageWindow.account_id == account.id))
        platform = session.get(PlatformBudget, window.window_key)
        print(f"Successes: {sum(results)}")
        print(f"Platform Settled: {platform.settled_micro}, Platform Reserved: {platform.reserved_micro}")
        print(f"Window Settled: {window.settled_micro}, Window Reserved: {window.reserved_micro}")

if __name__ == '__main__':
    test()
