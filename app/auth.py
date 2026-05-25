def login(token):
    user_id = decode_token(token)
    return {"user_id": user_id}
