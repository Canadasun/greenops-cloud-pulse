# Local sign-in stand-in. Build context = repository root, so the real token code from swa-api is used.
FROM node:22-alpine
WORKDIR /app
COPY local-auth/server.js local-auth/
COPY swa-api/src/token.js swa-api/src/
USER node
CMD ["node", "local-auth/server.js"]
