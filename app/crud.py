from sqlalchemy import select, desc, delete

from models import users, devices, measurements


# create user 
def create_user(session, data):
    query = users.insert().values(data)
    result = session.execute(query)
    session.commit()
    return result


#delete user
def remove_user(session, id):
    query = delete(users).where(users.c.id == id)
    result = session.execute(query)
    session.commit()
    return result.rowcount


def update_user(session, user_id, data: dict):
    query = users.update().where(users.c.id == user_id).values(data)
    result = session.execute(query)
    session.commit()
    return result


# find user by email/login
def find_user(session, email):
    query = select(users).where(users.c.email == email)
    result = session.execute(query).mappings().first()
    return result



def find_user_by_id(session, id):
    selected_columns = [col for col in users.c if col.name != 'hashed_password']
    query = select(*selected_columns).where(users.c.id == id)
    result = session.execute(query).mappings().first()
    return result 


def create_device(session, data):
    query = devices.insert().values(data)
    result = session.execute(query)
    session.commit()
    return result 


def update_device(session, device_id, user_id, data: dict):
    query = devices.update().where((devices.c.id == device_id) &
                                   (devices.c.user_id == user_id)).values(data)
    result = session.execute(query)
    session.commit()
    return result.rowcount


def remove_device(session, device_id, user_id):
    query = delete(devices).where((devices.c.id == device_id) & (devices.c.user_id == int(user_id)))
    result = session.execute(query)
    session.commit()
    return result.rowcount


def find_devices(session, user_id):
    query = select(devices).where(devices.c.user_id == user_id)
    result = session.execute(query).mappings().fetchall()
    return result


def find_device_by_id(session, device_id):
    query = select(devices).where(devices.c.id == device_id)
    result = session.execute(query).mappings().first()
    return result


def find_device_token(session, token):
    query = select(devices).where(devices.c.token == token)
    result = session.execute(query).mappings().first()
    return result


def add_measurements(session, data):
    query = measurements.insert().values(data)
    result = session.execute(query)
    session.commit()
    return result 


def find_measurements(session, device_id, period):
    query = (
        select(measurements).where(
        (measurements.c.device_id == device_id) & 
        (measurements.c.received_at >= period)
        ).order_by(desc(measurements.c.received_at))
    )
    result = session.execute(query).mappings().all()
    return result


def get_recent_measurement(session, device_id):
    query = select(measurements).where(measurements.c.device_id == device_id).order_by(desc(measurements.c.received_at)).limit(1)
    result =  session.execute(query).mappings().first()
    return result


def get_status(session, chat_id):
    result = {}

    query = select(users.c.id).where(users.c.tg_chat_id == chat_id)
    user_row = session.execute(query).first()
    if not user_row:
        return {"error": "User not registered"}
    user_id = user_row[0]
    query = select(devices).where(devices.c.user_id == user_id)
    device_rows = session.execute(query).mappings().all()
    for device in device_rows:
        query = select(measurements).where(measurements.c.device_id == device['id']).order_by(desc(measurements.c.received_at)).limit(1)
        metric = session.execute(query).mappings().first()
        result[device['name']] = dict(metric) if metric else None

    return result

def save_telegram_link(session, link, user_id):
    query = users.update().where(users.c.id == user_id).values(tg_link=link)
    result = session.execute(query)
    session.commit()
    return result 


def find_user_by_link(session, link):
    query = select(users).where(users.c.tg_link == link)
    result = session.execute(query).first()
    return result 


def save_chat_id(session, chat_id, user_id):
    query = users.update().where(users.c.id == user_id).values(tg_chat_id = chat_id)
    result = session.execute(query)
    session.commit()
    return result 


def get_chat_id(session, user_id):
    query = select(users.c.tg_chat_id).where(users.c.id == user_id)
    result = session.execute(query)
    return result.scalar_one_or_none() 


def delete_old_measurements(session, cutoff):
    query = delete(measurements).where(measurements.c.received_at < cutoff)
    result = session.execute(query)
    session.commit()
    return result.rowcount