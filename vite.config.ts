import {defineConfig} from 'vite';
import mcPlugin from '@motion-canvas/vite-plugin';

const motionCanvas = (mcPlugin as any).default || mcPlugin;

export default defineConfig({
  plugins: [
    motionCanvas({
      project: [
        './motioncanvas/project.ts',
      ],
    }),
  ],
  resolve: {
    alias: {
      '@': '/motioncanvas',
    },
  },
  server: {
    port: 9000,
    open: false,
  },
});
