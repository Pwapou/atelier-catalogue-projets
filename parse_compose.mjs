// Parse configuration as data only: no interpolation, environment files, Docker or network.
import { parseDocument } from 'yaml';
let input='';
for await (const chunk of process.stdin) input+=chunk;
const scalar=value=>['string','number','boolean'].includes(typeof value)?String(value).slice(0,1000).replace(/(https?:\/\/)[^/@\s]+@/g,'$1[identifiants masqués]@'):null;
const names=value=>Array.isArray(value)?value.map(scalar).filter(Boolean):value&&typeof value==='object'?Object.keys(value):[];
const list=value=>value==null?[]:Array.isArray(value)?value:[value];
const volume=v=>typeof v==='string'?scalar(v):v&&typeof v==='object'?{type:scalar(v.type),source:scalar(v.source),target:scalar(v.target),readOnly:v.read_only===true}:null;
const port=p=>typeof p==='string'||typeof p==='number'?scalar(p):p&&typeof p==='object'?{target:scalar(p.target),published:scalar(p.published),hostIp:scalar(p.host_ip),protocol:scalar(p.protocol)}:null;
function parse(file){
  try{
    const doc=parseDocument(file.content,{strict:true,uniqueKeys:true,merge:true});
    if(doc.errors.length)return {source:file.source,services:[],error:'YAML invalide ou non pris en charge.'};
    const data=doc.toJS({maxAliasCount:100});
    if(!data||typeof data!=='object')return {source:file.source,services:[],error:'Configuration YAML non reconnue.'};
    const services=Object.entries(data.services||{}).flatMap(([name,s])=>{
      if(!s||typeof s!=='object')return [];
      const build=typeof s.build==='string'?{context:scalar(s.build)}:s.build&&typeof s.build==='object'?{context:scalar(s.build.context),dockerfile:scalar(s.build.dockerfile),target:scalar(s.build.target)}:null;
      const h=s.healthcheck;
      const limits=s.deploy?.resources?.limits||{};
      return [{name,source:file.source,image:scalar(s.image),containerName:scalar(s.container_name),build,
        ports:list(s.ports).map(port).filter(Boolean),expose:list(s.expose).map(scalar).filter(Boolean),
        volumes:list(s.volumes).map(volume).filter(Boolean),tmpfs:list(s.tmpfs).map(scalar).filter(Boolean),networks:names(s.networks),networkMode:scalar(s.network_mode),
        dependsOn:names(s.depends_on),profiles:names(s.profiles),restart:scalar(s.restart),readOnly:s.read_only===true,
        healthcheck:h&&typeof h==='object'?{declared:true,disabled:h.disable===true||h.test==='NONE'||h.test?.[0]==='NONE',interval:scalar(h.interval),timeout:scalar(h.timeout),retries:scalar(h.retries),startPeriod:scalar(h.start_period)}:null,
        resources:{memory:scalar(s.mem_limit??limits.memory),cpus:scalar(s.cpus??limits.cpus)},
        commandDeclared:s.command!=null,entrypointDeclared:s.entrypoint!=null}];
    });
    const resources=(value)=>value&&typeof value==='object'?Object.entries(value).map(([name,r])=>({name,driver:scalar(r?.driver),external:r?.external===true,internal:r?.internal===true})):[];
    return {source:file.source,name:scalar(data.name),services,networks:resources(data.networks),volumes:resources(data.volumes),
      includesDeclared:data.include!=null,warning:doc.warnings.length?'Certaines balises YAML ne sont pas interprétées.':null};
  }catch{return {source:file.source,services:[],error:'Configuration non analysable (syntaxe ou limite de résolution des alias).'};}
}
process.stdout.write(JSON.stringify(JSON.parse(input).files.map(parse)));
