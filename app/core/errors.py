from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def is_html_request(request: Request) -> bool:
    accept = request.headers.get('accept', '')
    return 'text/html' in accept


def is_admin_path(request: Request) -> bool:
    return request.url.path.startswith('/admin')


def is_api_path(request: Request) -> bool:
    return request.url.path.startswith('/api')


def install_auth_exception_handlers(app):
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # только 401 перехватываем “по-особенному”
        if exc.status_code == 401:
            # API пусть получает JSON (как сейчас)
            if is_api_path(request) or not is_html_request(request):
                return JSONResponse({'detail': exc.detail}, status_code=401)
            
            # UI редиректим
            if is_admin_path(request):
                return RedirectResponse(url='/admin/login', status_code=302)
            return RedirectResponse(url='/', status_code=302)
        
        # остальное — как обычно
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
