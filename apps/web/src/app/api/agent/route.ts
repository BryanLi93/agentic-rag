// 过渡期停用旧入口；确认无外部调用后可移除此路由。
export async function POST() {
  return new Response("此入口已停用，请使用 /api/chat", { status: 410 });
}
