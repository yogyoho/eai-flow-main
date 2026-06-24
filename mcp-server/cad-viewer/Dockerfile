# CAD Viewer — text-to-cad's own 3D viewer.
# Node-only: server.mjs is an esbuild bundle (all deps inlined), dist/ is the
# pre-built three.js frontend. No npm install. STEP regeneration (python cadpy)
# is only invoked when a GLB sidecar is missing — we always emit GLB via
# create_step --glb, so node-only viewing works.
FROM node:22-alpine

WORKDIR /app
COPY viewer/ ./viewer/

EXPOSE 4178
# --dir /data = shared user-data (same mount as text-to-cad-mcp / cad-mcp).
CMD ["node", "viewer/backend/server.mjs", "--host", "0.0.0.0", "--port", "4178", "--dir", "/data"]
