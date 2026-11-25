import { getPageUser } from "@/lib/page-auth";
import { ExamRunner } from "@/components/ExamRunner";

export const dynamic = "force-dynamic";

export default async function ExamPage({
  params,
}: {
  params: Promise<{ attemptId: string }>;
}) {
  await getPageUser();
  const { attemptId } = await params;
  return <ExamRunner attemptId={attemptId} />;
}
