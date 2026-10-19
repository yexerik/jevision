/**
 * Verify real Vite configuration keeps credentials out of browser environment
 * values and prevents development HTTP access to private project-root files.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'vite';

test('Vite excludes private environment values and root files while serving frontend modules',async()=>{
  const key='VITE_TYPESAFE_API_KEY';
  const previous=process.env[key];
  const sentinel='fixture-publication-'+'private-value';
  process.env[key]=sentinel;
  const fixture=await mkdtemp(join(tmpdir(),'jevision-publication-'));
  const privateContent='fixture-private-file-content';
  let server;
  try {
    server=await createServer({
      configFile:fileURLToPath(new URL('../vite.config.js',import.meta.url)),
      logLevel:'silent',server:{port:0},
    });
    await server.listen();
    const port=server.httpServer.address().port;
    const base=`http://127.0.0.1:${port}`;
    assert.equal(Object.hasOwn(server.config.env,key),false);
    assert.equal(JSON.stringify(server.config.env).includes(sentinel),false);
    for(const route of ['/app.js','/api.js','/@vite/client']){
      const response=await fetch(base+route);
      assert.equal(response.status,200,route);
      assert.equal((await response.text()).includes(sentinel),false);
    }
    // A fresh clone has no library metadata or .env. Create real private files
    // outside the frontend root instead of relying on a developer's local data.
    for(const name of ['.env','.git/config','.jev-image-data/library.json','server.py']){
      const path=join(fixture,name);
      await mkdir(join(path,'..'),{recursive:true});
      await writeFile(path,privateContent);
      const response=await fetch(base+'/@fs'+path);
      assert.equal(response.status,403,name);
      const body=await response.text();
      assert.equal(body.includes(sentinel),false);
      assert.equal(body.includes(privateContent),false);
    }
  } finally {
    if(server)await server.close();
    await rm(fixture,{recursive:true,force:true});
    if(previous===undefined)delete process.env[key];else process.env[key]=previous;
  }
});
