import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import path from 'node:path';

// Use svelte() directly instead of sveltekit().
// sveltekit() registers Vite 6 environment entries that Vitest 2.x cannot
// resolve, causing "Cannot create proxy with a non-object as target" when
// vite-plugin-svelte attempts CSS preprocessing on <style> blocks.
//
// We also disable CSS preprocessing via vitePreprocess({ style: false })
// because Vite 6's preprocessCSS requires `config.environments.client` which
// Vitest 2.x's resolved config does not provide.
export default defineConfig({
  plugins: [
    svelte({
      hot: false,
      // Prevent loading svelte.config.js which includes vitePreprocess()
      // with CSS enabled. Vite 6's preprocessCSS needs `config.environments.client`
      // which Vitest 2.x does not provide, causing a Proxy creation error.
      configFile: false,
      preprocess: vitePreprocess({ style: false }),
    }),
  ],
  resolve: {
    // Ensure Svelte resolves to its client-side (browser) bundle, not the
    // server bundle. Without this, `mount(...)` throws "not available on the server".
    conditions: ['browser', 'svelte'],
    alias: {
      // Reproduce the SvelteKit aliases so test imports resolve correctly.
      $lib: path.resolve(__dirname, 'src/lib'),
      '$app/environment': path.resolve(
        __dirname,
        'node_modules/@sveltejs/kit/src/runtime/app/environment/index.js',
      ),
      '$app/navigation': path.resolve(
        __dirname,
        'node_modules/@sveltejs/kit/src/runtime/app/navigation.js',
      ),
      '$app/stores': path.resolve(
        __dirname,
        'node_modules/@sveltejs/kit/src/runtime/app/stores.js',
      ),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    setupFiles: ['src/test/setup.ts'],
    clearMocks: true,
  },
});
