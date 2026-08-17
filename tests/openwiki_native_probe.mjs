import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
const root=path.resolve(process.argv[2]);
const modulePath=path.resolve("node_modules/openwiki/dist/okf/frontmatter.js");
const { validateOkfFrontmatter }=await import(pathToFileURL(modulePath).href);
const files=[];
function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name); if(e.isDirectory()) walk(p); else if(e.isFile()&&e.name.endsWith(".md")&&!['index.md','log.md'].includes(e.name)) files.push(p)}}
walk(root); let failed=0;
for(const file of files){const result=validateOkfFrontmatter(fs.readFileSync(file,"utf8")); if(!result.valid){console.error(file,result.issues); failed++;}}
console.log(`OpenWiki validateOkfFrontmatter: ${files.length} concept pages checked`);
if(failed) process.exit(1);
