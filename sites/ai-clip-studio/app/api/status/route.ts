import {NextResponse} from "next/server";
const backend=()=>process.env.RENDER_BACKEND_URL||"http://127.0.0.1:8787";
export async function GET(request:Request){const id=new URL(request.url).searchParams.get("id")||"";try{const r=await fetch(`${backend()}/api/status?id=${encodeURIComponent(id)}`,{cache:"no-store"});return new NextResponse(await r.text(),{status:r.status,headers:{"content-type":"application/json"}})}catch{return NextResponse.json({status:"failed",message:"Mất kết nối render backend"},{status:503})}}
