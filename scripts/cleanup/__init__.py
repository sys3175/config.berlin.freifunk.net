from datetime import datetime, timedelta
from app.utils import get_api
from app.models import db, IPRequest

def delete_unconfirmed_requests(hours):
    current_time = datetime.utcnow()
    two_days_ago = current_time - timedelta(hours=hours)
    qry = IPRequest.query.filter(IPRequest.created_at <
        two_days_ago).filter(IPRequest.verified == False)

    print("Found %d outdated entries." % qry.count())
    for r in qry.all():
        print("\t * %s ...\t DELETED" % r.email)
        db.session.delete(r)

    db.session.commit()
