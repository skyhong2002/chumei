# Feed window and publication evidence validation

Desktop feed columns start with twelve posts, matching the existing server-rendered
window. Each column owns its loaded count and vertical position. Loading more only
repaints that column; changing its filter starts a new window. Same-layout resize
keeps the DOM and input focus. Crossing the mobile breakpoint preserves desktop
loaded counts, vertical position and horizontal deck position; navigation buttons
bind the current deck after rebuilding it. Mobile keeps its existing thirty-item
overview. Server-rendered desktop pagination offers the remainder even when a
source has fewer than thirty posts.

Source and organization update dates use valid publication evidence, falling back
to stable first-seen/fetch evidence. Future activity dates never become the current
build time. Missing evidence stays unknown. Timestamp offsets are normalized to
Taipei before sorting. NYCU LIFE adapter and legacy inbox integration is a separate
integration step; this change does not rewrite any collected records.

Validation on 2026-10-18: isolated scripts/ci_check.py passed 394 Python/JS tests,
SEO/output corruption rejection, and Chromium at 390/1024/1440/1920 pixels. Browser
assertions cover independent pagination, unchanged neighbour DOM, filter resets,
same-layout resize, mobile/desktop restoration, current-deck arrow controls,
vertical wheel containment, sticky headers and keyboard filter navigation. All
data is synthetic; external requests are blocked. No production publish occurred.

Independent source review found the horizontal-position restoration gap; the final
patch adds desktop-specific state and a browser regression. This validation makes
no production latency or real-user performance claim.
