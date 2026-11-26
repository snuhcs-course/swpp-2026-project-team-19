"""What the web pages served by the API share: the operator dashboard (/admin), the owner web (/owner) and
the privacy policy (/privacy), which has a stricter policy of its own.

/admin and /owner sign in with Supabase Google login in the browser and call the spec APIs with the access
token, like the Android app. They add no API: each page's `config.js` only hands it the public settings.
/privacy has no sign-in and no `config.js`.
"""

import json
import os

from starlette.responses import Response

from app.core.auth_config import load_supabase_auth_settings

# The supabase-js build the admin page loads, pinned with Subresource Integrity.
SUPABASE_JS_ORIGIN = "https://cdn.jsdelivr.net"
# The Kakao Maps JavaScript SDK (map and address search) and the scripts it loads.
# No scheme: the SDK loads its files over the page's scheme, so this allows https on the server and
# http on a local http://localhost page. Kakao asks CSP users to allow every kakaocdn.net subhost, since
# the SDK may pick another one (https://devtalk.kakao.com/t/api-daumcdn-net/152465).
KAKAO_CDN_HOSTS = "*.kakaocdn.net *.daumcdn.net"

NO_CACHE = "no-cache"


def content_security_policy() -> str:
    settings = load_supabase_auth_settings()
    supabase = f" {settings.url}" if settings else ""
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {SUPABASE_JS_ORIGIN} dapi.kakao.com {KAKAO_CDN_HOSTS}",
            # The Kakao map adds an inline <style> that changes with its version, so no hash. Scripts stay
            # strict, and the pages put data on the page only as text.
            "style-src 'self' 'unsafe-inline'",
            # Menu photos are signed object-storage URLs (S3) or /media paths on this server (local),
            # and Kakao map tiles and marker images come from kakaocdn.net and daumcdn.net hosts. blob: is
            # for the owner web's previews of the photos picked on the device (URL.createObjectURL), which
            # only the page itself can create.
            f"img-src 'self' https: data: blob: {KAKAO_CDN_HOSTS}",
            f"connect-src 'self'{supabase} dapi.kakao.com",
            "frame-ancestors 'none'",
            "base-uri 'none'",
            "form-action 'self'",
        ]
    )


def privacy_content_security_policy() -> str:
    """The privacy policy page (/privacy): its own stylesheet and links, and nothing else. No script runs."""
    return "; ".join(
        [
            "default-src 'none'",
            "style-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'none'",
            "form-action 'none'",
        ]
    )


def add_page_headers(response: Response, cache_control: str = NO_CACHE, policy: str | None = None) -> Response:
    response.headers["Content-Security-Policy"] = policy or content_security_policy()
    # Signed photo URLs and the OAuth callback must not leak through the Referer header.
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # By default a new deploy takes effect on the next load.
    response.headers["Cache-Control"] = cache_control
    return response


def public_config() -> dict[str, str | None]:
    """The public settings a page needs: the Supabase project URL and publishable (anon) key, and the
    Kakao JavaScript key, which works only on the domains registered in Kakao Developers."""
    settings = load_supabase_auth_settings()
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    return {
        "supabaseUrl": settings.url if settings and key else None,
        "supabasePublishableKey": key if settings and key else None,
        "kakaoJavascriptKey": os.getenv("KAKAO_JAVASCRIPT_KEY", "").strip() or None,
    }


def config_script(global_name: str) -> Response:
    """`public_config()` as a script that sets `window.<global_name>`."""
    body = f"window.{global_name} = {json.dumps(public_config())};\n"
    return add_page_headers(Response(body, media_type="text/javascript"))
