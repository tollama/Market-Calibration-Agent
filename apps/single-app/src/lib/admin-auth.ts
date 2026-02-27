import { NextRequest, NextResponse } from 'next/server';

import { withAdvisory } from './advisory-policy';

function unauthorizedResponse(message: string, scope: string) {
  return NextResponse.json(withAdvisory(scope, { ok: false, message }), { status: 401 });
}

function forbiddenResponse(message: string, scope: string) {
  return NextResponse.json(withAdvisory(scope, { ok: false, message }), { status: 403 });
}

export function requireAdminAuth(req: NextRequest, scope: string): NextResponse | null {
  const expectedToken = process.env.ADMIN_API_TOKEN?.trim();
  if (!expectedToken) {
    return NextResponse.json(
      withAdvisory(scope, {
        ok: false,
        message: 'Server is not configured for admin authentication',
      }),
      { status: 503 }
    );
  }

  const authorization = req.headers.get('authorization');
  if (!authorization) {
    return unauthorizedResponse('Missing Authorization header', scope);
  }

  const [scheme, token] = authorization.split(' ');
  if (scheme !== 'Bearer' || !token) {
    return unauthorizedResponse('Authorization header must be Bearer token', scope);
  }

  if (token !== expectedToken) {
    return forbiddenResponse('Invalid admin token', scope);
  }

  return null;
}
