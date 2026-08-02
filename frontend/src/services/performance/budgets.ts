export const performanceBudgetsMs = { cold_start:3000,reader_open:500,resume:400,page_turn:80,theme_reflow:150,selection_toolbar:120,dictionary_cached:200,indexed_search:200,import_5mb:2000,home_interaction:100,annotation_save:100 } as const;
export type PerformanceOperation = keyof typeof performanceBudgetsMs;
export interface PerformanceSample { operation:PerformanceOperation; durationMs:number; timestamp:number; }
const samples:PerformanceSample[]=[];
export function recordPerformance(operation:PerformanceOperation,durationMs:number):void { samples.push({operation,durationMs,timestamp:Date.now()}); if(samples.length>1000)samples.shift(); }
export async function measurePerformance<T>(operation:PerformanceOperation,work:()=>Promise<T>|T):Promise<T> { const start=performance.now(); try{return await work();}finally{recordPerformance(operation,performance.now()-start);} }
export function performanceSamples():PerformanceSample[]{return [...samples];}
declare global { interface Window { __BOOKBUDDY_PERF__?:()=>PerformanceSample[]; } }
if(typeof window!=="undefined") window.__BOOKBUDDY_PERF__=performanceSamples;
