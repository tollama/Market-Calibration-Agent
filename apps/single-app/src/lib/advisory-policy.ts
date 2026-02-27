export type AdvisoryDisclaimer = {
  advisoryOnly: true;
  message: string;
  legal: string;
  notInvestmentAdvice: true;
  notLegalAdvice: true;
  userResponsibility: string;
};

export type AdvisoryScopeMeta = {
  scope: string;
  executionEnabled: boolean;
};

const DIRECT_TRADING_PATTERNS = [
  /지금\s*매수/gi,
  /지금\s*매도/gi,
  /즉시\s*매수/gi,
  /즉시\s*매도/gi,
  /당장\s*매수/gi,
  /당장\s*매도/gi,
  /buy\s*now/gi,
  /sell\s*now/gi,
  /strong\s*buy/gi,
  /strong\s*sell/gi,
];

const BLOCKED_TEXT = '직접 거래 지시 문구는 제공하지 않습니다. 판단은 사용자 책임입니다.';

export function getAdvisoryDisclaimer(scope: string): AdvisoryDisclaimer {
  return {
    advisoryOnly: true,
    message: `본 서비스(${scope})는 정보 제공 전용이며 매매 실행/중개를 제공하지 않습니다.`,
    legal: '법률·세무·회계 자문이 아니며, 관할 규제 준수는 사용자 및 운영 주체의 책임입니다.',
    notInvestmentAdvice: true,
    notLegalAdvice: true,
    userResponsibility: '모든 의사결정(투자·거래·규제 대응 포함)은 사용자 책임입니다.',
  };
}

export function sanitizeAdvisoryText(text: string): string {
  if (!text) return text;

  let sanitized = text;
  for (const pattern of DIRECT_TRADING_PATTERNS) {
    sanitized = sanitized.replace(pattern, BLOCKED_TEXT);
  }
  return sanitized;
}

export function isExecutionApiEnabled(): boolean {
  return process.env.EXECUTION_API_ENABLED === 'true';
}

export function getAdvisoryMeta(scope: string): AdvisoryScopeMeta {
  return {
    scope,
    executionEnabled: isExecutionApiEnabled(),
  };
}

export function withAdvisory<T extends Record<string, unknown>>(
  scope: string,
  payload: T
): T & { advisory: AdvisoryScopeMeta; disclaimer: AdvisoryDisclaimer } {
  return {
    ...payload,
    advisory: getAdvisoryMeta(scope),
    disclaimer: getAdvisoryDisclaimer(scope),
  };
}
