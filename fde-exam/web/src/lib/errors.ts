export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(code: string, message: string, status = 400, details?: unknown) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export class PoolInsufficientError extends ApiError {
  constructor(message = "可用题目不足，请联系管理员补充题库") {
    super("POOL_INSUFFICIENT", message, 409);
  }
}
