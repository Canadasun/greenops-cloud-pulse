// Azure Functions registration: GET /api/token on the dashboard's own address.
const { app } = require('@azure/functions');
const { tokenResponse } = require('./token');
app.http('token', { methods: ['GET'], authLevel: 'anonymous', route: 'token',
  handler: async request => tokenResponse(request.headers.get('x-ms-client-principal') || '', process.env.SESSION_SIGNING_KEY) });
