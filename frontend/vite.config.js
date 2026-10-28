import { defineConfig } from 'vite';
export default defineConfig({server:{proxy:{'/api':`http://127.0.0.1:${process.env.BRAINSTORM_BACKEND_PORT || '8000'}`}}});
