import sys
sys.path.insert(0, 'd:/eai/eai-flow-main/backend')

try:
    from app.extensions.dept.routers import router as dept_router
    print(f"dept_router prefix: {dept_router.prefix}")
except Exception as e:
    print(f"dept import failed: {type(e).__name__}: {e}")

try:
    from app.extensions.docmgr.routers import router as docmgr_router
    print(f"docmgr_router prefix: {docmgr_router.prefix}")
except Exception as e:
    print(f"docmgr import failed: {type(e).__name__}: {e}")

try:
    from app.gateway.app import create_app
    app = create_app()
    paths = [r.path for r in app.routes]
    dept_paths = [p for p in paths if 'departments' in p and 'user' not in p]
    docmgr_paths = [p for p in paths if 'docmgr' in p]
    print(f"\nApp routes (direct test):")
    print(f"  Departments (non-user): {dept_paths}")
    print(f"  Docmgr: {docmgr_paths}")
except Exception as e:
    print(f"create_app failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
