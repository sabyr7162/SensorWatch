from fastapi import APIRouter, HTTPException, Depends, Form, Header, Query, BackgroundTasks, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session 
from sqlalchemy.exc import IntegrityError
from pwdlib import PasswordHash

from datetime import datetime, timezone, timedelta

import secrets 
import logging
import html

from database import get_db
from security import create_token, token_verify, is_valid_email, limiter, too_many_failures, failures
from schemas import *
from crud import *
from services import check_threshold
from alert import send_alert


password_hash = PasswordHash.recommended()
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/users/login')
logger = logging.getLogger(__name__)

@router.post('/users', status_code=200)
@limiter.limit("5/minutes;20/hour")
def register(request: Request, body: UserRegisterRequest, session: Session = Depends(get_db)):
    # check email regex
    data = body.model_dump()
    data['email'] = data['email'].strip().lower()
    if not is_valid_email(data['email']):  
        raise HTTPException(status_code=400, detail="Invalid email format")
    
    if find_user(session, data['email']):
       raise HTTPException(status_code=403, detail='user by this email already registered')
    
    hashed_password = password_hash.hash(body.password)
    data['hashed_password'] = hashed_password
    data.pop('password')
    data['created_at'] = datetime.now(timezone.utc)
    # create user, add to db
    try:
        result = create_user(session, data)
    except IntegrityError:
        raise HTTPException(status_code=403, detail="User already exists")
    user_id = result.inserted_primary_key[0]

    return {
        "status": "success",
        "message": "User registered successfully",
        "user_id": user_id}


@router.post('/users/login', status_code=200)
@limiter.limit("5/minutes;30/hour")
def login(request: Request,
        username: str = Form(...), 
        password: str = Form(...), 
        session: Session = Depends(get_db)):
    # check if user in database
    username = username.strip().lower()
    if too_many_failures(username):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later")
    data = find_user(session, username)
    if not data or not password_hash.verify(password, data['hashed_password']):
        failures.setdefault(username, []).append(datetime.now(timezone.utc))
        raise HTTPException(status_code=404, detail="Invalid login or password")
    user_id = data['id']
    token = create_token(user_id)
    failures.pop(username, None)
    return {'access_token': token, 'token_type': 'bearer'}


@router.get('/users', status_code=200)
def get_me(token: str = Depends(oauth2_scheme), session: Session = Depends(get_db)):
    payload = token_verify(token)
    user_id = payload.get('sub')
    data = find_user_by_id(session, user_id)
    if not data:
        raise HTTPException(status_code=404, detail='User not found')
    return data


@router.patch('/users', status_code=200)
def patch_user(body: UserPatchRequest, 
            token: str = Depends(oauth2_scheme), 
            session: Session = Depends(get_db)):
    payload = token_verify(token)
    user_id = payload.get('sub')
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if 'email' in data:
        data['email'] = data['email'].strip().lower()
        if not is_valid_email(body.email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        if find_user(session, data['email']):
            raise HTTPException(status_code=403, detail='email already exists')
    if 'password' in data:
        data['hashed_password'] = password_hash.hash(data['password'])
    data.pop('password', None)
    try:
        result = update_user(session, user_id, data)
    except IntegrityError:
        raise HTTPException(status_code=403, detail="User  already exists")
    if not result:
        raise HTTPException(status_code=404, detail="User not found or no changes applied")
    return {
        'status': 'success',
        'updated': result.rowcount
    }

@router.delete('/users', status_code=200)
def delete_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_db)):
    payload = token_verify(token)
    user_id = payload.get('sub')
    result = remove_user(session, user_id)
    if not result:
        raise HTTPException(status_code=404, detail='User not found')
    return {'status': 'success'}


@router.post('/users/device', status_code=201)
def add_device(body: DeviceRegisterRequest, session: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = token_verify(token)
    user = int(payload.get('sub'))
    data = body.model_dump()
    data['user_id'] = user

    # create token 
    data['token'] = secrets.token_hex(32)
    data['created_at'] = datetime.now(timezone.utc)
    try:
        result = create_device(session, data)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=403, detail="Device ID already exists")
    return {
        "status": "success",
        "message": "Device registered successfully",
        "device_id": data['device_id'],
        "token": data['token'] }


@router.patch('/users/device/{device_id}', status_code=200)
def patch_device(device_id: int,
                body:DevicePatchRequest,
                token: str = Depends(oauth2_scheme), 
                session: Session = Depends(get_db)):
    payload = token_verify(token)
    user_id = int(payload.get('sub'))
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        result = update_device(session, device_id, user_id, data)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=403, detail="Device ID already exists")
    if not result:
        raise HTTPException(status_code=404, detail="Device not found or changes are not applied")
    return {
        "status": "Success",
        "updated": result
    }


@router.delete('/users/device/{device_id}', status_code=200)
def delete_device(device_id: int, token: str = Depends(oauth2_scheme), session: Session = Depends(get_db)):
    payload = token_verify(token)
    user_id = payload.get('sub')
    result = remove_device(session, device_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "success"}



@router.get('/users/device', status_code=200)
def get_devices(token: str = Depends(oauth2_scheme), session: Session = Depends(get_db)):
    payload = token_verify(token)
    devices = find_devices(session, payload.get('sub'))
    return {'devices': devices}


@router.get('/users/device/{device_id}', status_code=200)
def get_device(device_id: int, 
               token: str = Depends(oauth2_scheme), 
               session: Session = Depends(get_db)
               ):
    payload = token_verify(token)
    user_id = payload.get('sub')
    device = find_device_by_id(session, device_id)

    if not device or device['user_id'] != int(user_id):
        raise HTTPException(status_code=404, detail='Device not found')
    return device
 
# get measurements from device
@router.post('/users/device/measurements', status_code=200)
async def recieve_measurements(
    body: MeasurementsPostRequest, 
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    x_device_token: str = Header(...)
    ):

    device = find_device_token(session, x_device_token)
    if not device:
        raise HTTPException(status_code=403, detail="Access denied")
    if not device['status']:
        raise HTTPException(status_code=403, detail='Device is disabled')
    
    data = body.model_dump()
    data.pop('id', None)
    data['timestamp'] = datetime.now(timezone.utc)
    data['device_id'] = device['id']
    data['received_at'] = datetime.now(timezone.utc)
    if device['thresholds']:
        triggerd_alerts = check_threshold(device['thresholds'], data['metrics'])

    add_measurements(session, data)

    if triggerd_alerts:
        user_id = device['user_id']
        chat_id = get_chat_id(session, user_id)
        if chat_id:
            for message in triggerd_alerts.values():
                msg = (
                    f"<b>🚨ALERT: {html.escape(device.get('name', 'Device'))}</b>\n"
                    f"{html.escape(message)}"
                )
                background_tasks.add_task(send_alert, chat_id, msg)

    return {"status": "success", "alerts": list(triggerd_alerts.keys())}


# get measuremnts from db 
@router.get('/users/device/{device_id}/measurements')
def get_measurements(
    device_id: int,
    period: str = Query("24h", description="Filter period: 1h, 24h, 7d, 30d"),
    token: str = Depends(oauth2_scheme), 
    session: Session = Depends(get_db)):

    device = find_device_by_id(session, device_id)
    payload = token_verify(token)
    user_id = payload.get('sub')
    
    if not device or device['user_id'] != int(user_id):
        raise HTTPException(status_code=404, detail="Device not found or access denied")

    now = datetime.now(timezone.utc)
    match period: 
        case '1h':
            cutoff = now - timedelta(hours=1)
        case '24h':
            cutoff = now - timedelta(days=1)
        case '7d':
            cutoff = now - timedelta(days=7)
        case '30d':
            cutoff = now - timedelta(days=30)
        case _:
            cutoff = now - timedelta(days=1)

    measurements = find_measurements(session, device_id, cutoff)
    step = max(1, len(measurements) // 1500)
    return [dict(row) for row in reversed(measurements[::step])]
    

# get latests measurements from database     
@router.get('/users/device/{device_id}/measurements/latest')
def get_device_status(device_id: int, session: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    payload = token_verify(token)
    device = find_device_by_id(session, device_id)
    user_id = payload.get('sub')
    if not device or device['user_id'] != int(user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    latest = get_recent_measurement(session, device_id)
    if not latest:
        raise HTTPException(status_code=404, detail='No measurements found')
    return dict(latest)


@router.post('/users/telegram/link', status_code=200)
def get_telegram_linK(
    token: str = Depends(oauth2_scheme), session: Session = Depends(get_db)
        ):
    payload = token_verify(token)
    user_id = int(payload.get('sub'))

    link = secrets.token_urlsafe(16)
    bot_username = "HSalertdetectbot"
    # print(f"https://t.me/{bot_username}?start={link}")
    save_telegram_link(session, link, user_id)

    return {
        "telegram_url": f"https://t.me/{bot_username}?start={link}"
    }