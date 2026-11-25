import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";

export async function getPageUser() {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  return user;
}

export async function getAdminPageUser() {
  const user = await getPageUser();
  if (user.role !== "ADMIN") redirect("/");
  return user;
}
