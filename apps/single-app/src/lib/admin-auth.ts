import { NextRequest, NextResponse } from 'next/server';

function unauthorizedResponse(message: string) {
  return NextResponse.json({ ok: false, message }, { status: 401 });
}

function forbiddenResponse(message: string) {
  return NextResponse.json({ ok: false, message }, { status: 403 });
}

export function requireAdminAuth(req: NextRequest): NextResponse | null {
  const expectedToken = process.env.ADMIN_API_TOKEN?.trim();
  if (!expectedToken) {
    return NextResponse.json(
      {
        ok: false,
        message: 'Server is not configured for admin authentication',
      },
      { status: 503 }
    );
  }

  const authorization = req.headers.get('authorization');
  if (!authorization) {
    return unauthorizedResponse('Missing Authorization header');
  }

  const [scheme, token] = authorization.split(' ');
  if (scheme !== 'Bearer' || !token) {
    return unauthorizedResponse('Authorization header must be Bearer token');
  }

  if (token !== expectedToken) {
    return forbiddenResponse('Invalid admin token');
  }

  return null;
}
