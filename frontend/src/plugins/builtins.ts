import type { ReaderPluginManifest } from "./contracts";

export const builtinPlugins: ReaderPluginManifest[] = [
  { id:"reader-core",version:"1.0.0",apiVersion:"reader-plugin-v1",capabilities:["clipboard","annotations","search"],requiredBackendCapabilities:[],backgroundTaskTypes:["search_index"],panels:[{id:"annotations",label:"Notes & bookmarks"}],selectionActions:[
    {id:"copy",label:"Copy",order:40},{id:"highlight",label:"Highlight",order:50},{id:"underline",label:"Underline",order:60},{id:"note",label:"Note",order:70},{id:"search",label:"Search",order:80},
  ]},
  { id:"dictionary",version:"1.0.0",apiVersion:"reader-plugin-v1",capabilities:["dictionary"],requiredBackendCapabilities:["dictionary"],backgroundTaskTypes:[],panels:[],selectionActions:[{id:"dictionary",label:"Look up",order:10,capability:"dictionary"}] },
  { id:"story",version:"1.0.0",apiVersion:"reader-plugin-v1",capabilities:["story"],requiredBackendCapabilities:["chapter_analysis"],backgroundTaskTypes:["analysis"],panels:[],selectionActions:[] },
  { id:"characters",version:"1.0.0",apiVersion:"reader-plugin-v1",capabilities:["characters"],requiredBackendCapabilities:["dictionary"],backgroundTaskTypes:[],panels:[],selectionActions:[] },
  { id:"translation",version:"1.0.0",apiVersion:"reader-plugin-v1",capabilities:["translation"],requiredBackendCapabilities:["translation"],backgroundTaskTypes:["translation"],panels:[],selectionActions:[{id:"translate",label:"Translate",order:90,capability:"translation"}] },
  { id:"cypher",version:"0.1.0",apiVersion:"reader-plugin-v1",capabilities:["cypher"],requiredBackendCapabilities:["cypher"],backgroundTaskTypes:[],panels:[{id:"cypher",label:"Cypher"}],selectionActions:[] },
  { id:"timeline",version:"0.1.0",apiVersion:"reader-plugin-v1",capabilities:["timeline"],requiredBackendCapabilities:["timeline"],backgroundTaskTypes:[],panels:[{id:"timeline",label:"Timeline"}],selectionActions:[] },
  { id:"relationships",version:"0.1.0",apiVersion:"reader-plugin-v1",capabilities:["relationships"],requiredBackendCapabilities:["relationships"],backgroundTaskTypes:[],panels:[{id:"relationships",label:"Relationships"}],selectionActions:[] },
  { id:"web",version:"0.1.0",apiVersion:"reader-plugin-v1",capabilities:["web"],requiredBackendCapabilities:["web"],backgroundTaskTypes:["web"],panels:[],selectionActions:[] },
];
