import { NextResponse } from "next/server";

const backend = () => process.env.RENDER_BACKEND_URL || "http://127.0.0.1:8787";

export async function POST(request: Request) {
  try {
    const body = await request.text();
    const response = await fetch(`${backend()}/api/review-content`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json(
      { error: "Render backend chưa sẵn sàng để review nội dung" },
      { status: 503 },
    );
  }
}
