from fastapi.templating import Jinja2Templates
from fastapi import Request
from jinja2 import pass_context
from app.config import settings
from app.utils.ist_time import format_ist_datetime

templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

# Custom url_for helper with Jinja2 pass_context supporting both 'filename' (Flask) and 'path' (FastAPI)
@pass_context
def custom_url_for(context, name: str, **path_params):
    request = context.get("request")
    if "filename" in path_params and name == "static":
        path_params["path"] = path_params.pop("filename")
    
    if request:
        try:
            return request.url_for(name, **path_params)
        except Exception:
            pass

    # Safe fallback if route cannot be resolved
    if name == "static":
        p = path_params.get("path", "")
        return f"/static/{p.lstrip('/')}"
    return f"/{name}"

templates.env.globals["url_for"] = custom_url_for
templates.env.globals["format_ist_datetime"] = format_ist_datetime
templates.env.globals["app_name"] = settings.APP_NAME
templates.env.globals["min"] = min
templates.env.globals["max"] = max
templates.env.globals["round"] = round
templates.env.globals["float"] = float
templates.env.globals["int"] = int

# Forward & backward compatibility wrapper for TemplateResponse
_orig_template_response = templates.TemplateResponse

def universal_template_response(*args, **kwargs):
    """
    Supports both legacy Starlette (name, context, ...)
    and modern Starlette (request, name, context, ...).
    Automatically injects live platform settings (ai_enabled, ai_status, settings_version)
    into all rendered templates across all roles (consumer, farmer, delivery, admin, public).
    """
    from app.services.platform_settings_service import PlatformSettingsService
    is_ai_enabled = PlatformSettingsService.is_ai_enabled()
    ai_status = "connected" if is_ai_enabled else "disconnected"
    version = PlatformSettingsService.get_state_version()

    def _inject_defaults(ctx: dict):
        if isinstance(ctx, dict):
            # Always ensure template context reflects the true platform settings
            ctx["ai_enabled"] = is_ai_enabled
            ctx["ai_status"] = ai_status
            ctx["platform_settings_version"] = version

    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], dict):
        name = args[0]
        context = args[1]
        _inject_defaults(context)
        req = context.get("request")
        status_code = kwargs.get("status_code", args[2] if len(args) > 2 else 200)
        headers = kwargs.get("headers", None)
        return _orig_template_response(
            request=req,
            name=name,
            context=context,
            status_code=status_code,
            headers=headers
        )
    elif "context" in kwargs and isinstance(kwargs["context"], dict):
        _inject_defaults(kwargs["context"])
        if "request" not in kwargs:
            kwargs["request"] = kwargs["context"].get("request")
        return _orig_template_response(**kwargs)
    elif len(args) >= 3 and isinstance(args[2], dict):
        context = args[2]
        _inject_defaults(context)
        return _orig_template_response(*args, **kwargs)

    return _orig_template_response(*args, **kwargs)

templates.TemplateResponse = universal_template_response
