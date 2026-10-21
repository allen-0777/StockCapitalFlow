// VITE_API_KEY is visible in the client bundle; use only as a shared access gate.
export const apiKeyHeaders = import.meta.env.VITE_API_KEY
  ? { 'X-API-Key': import.meta.env.VITE_API_KEY }
  : {}
