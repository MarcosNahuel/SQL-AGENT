/**
 * /api/chat - Proxy endpoint for AI SDK v5 useChat
 *
 * This route:
 * 1. Receives POST from useChat hook
 * 2. Forwards to FastAPI backend /v1/chat/stream
 * 3. Pipes the streaming response back
 * 4. Adds AI SDK v5 protocol headers
 */
import { NextRequest } from 'next/server';

const BACKEND_STREAM_URL = process.env.BACKEND_STREAM_URL || 'http://localhost:8000/v1/chat/stream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    // Extract the last user message from useChat format
    const messages = body.messages || [];
    const lastMessage = messages[messages.length - 1];
    const question = lastMessage?.content || '';

    if (!question) {
      return new Response(
        JSON.stringify({ error: 'No question provided' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Forward to backend with streaming
    const backendResponse = await fetch(BACKEND_STREAM_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify({
        question,
        conversation_id: body.id,
        user_id: body.userId,
      }),
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      console.error('[api/chat] Backend error:', errorText);
      return new Response(
        JSON.stringify({ error: `Backend error: ${backendResponse.status}` }),
        { status: backendResponse.status, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Get the readable stream from backend
    const stream = backendResponse.body;
    if (!stream) {
      return new Response(
        JSON.stringify({ error: 'No stream from backend' }),
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Return streaming response with AI SDK v5 headers
    return new Response(stream, {
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
        // AI SDK v5 protocol header
        'x-vercel-ai-ui-message-stream': 'v1',
      },
    });
  } catch (error) {
    console.error('[api/chat] Error:', error);
    return new Response(
      JSON.stringify({ error: error instanceof Error ? error.message : 'Unknown error' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
