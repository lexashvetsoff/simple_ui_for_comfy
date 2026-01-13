from fastapi import Response


ACCESS_COOKIE = 'access_token'
REFRESH_COOKIE = 'refresh_token'


def _clear_auth_cookies(response: Response):
    response.delete_cookie(ACCESS_COOKIE, path='/')
    response.delete_cookie(REFRESH_COOKIE, path='/')


def _set_auth_cookies(
        response: Response,
        access_token: str,
        refresh_token: str
):
    response.set_cookie(key=ACCESS_COOKIE, value=access_token, httponly=True, samesite='lax')
    response.set_cookie(key=REFRESH_COOKIE, value=refresh_token, httponly=True, samesite='lax')


def _set_access_cookie(response: Response, access_token: str):
    response.set_cookie(key=ACCESS_COOKIE, value=access_token, httponly=True, samesite='lax')
