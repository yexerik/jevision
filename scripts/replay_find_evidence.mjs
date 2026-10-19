/** JSON stdin -> JSON stdout. No browser, transport, model calls or mutations. */
import { replayV5Evidence } from '../web/tools/find/evidence.js';
let input='';for await (const chunk of process.stdin) input+=chunk;
const jobs=JSON.parse(input);
const outputs=jobs.map(({result,config})=>{
  const replay=replayV5Evidence(result,config);
  return {config:replay.config,decisions:replay.decisions,
    stages:{valid:result.observations.map(o=>o.box),
      discovery:result.observations.filter(o=>replay.decisions.find(d=>d.observationId===o.id).discovery).map(o=>o.box),
      verified:replay.accepted.map(o=>o.box),registered:replay.registry.objects.map(o=>o.box),located:replay.boxes.map(o=>o.box),review:replay.reviewBoxes.map(o=>o.box)},
    missingVerification:replay.missingVerification,missingIdentity:replay.missingIdentity,scope:replay.scope};
});
process.stdout.write(JSON.stringify(outputs));
