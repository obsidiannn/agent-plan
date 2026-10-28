import Link from "next/link";

export default function Forbidden() {
    return (
        <div className="min-h-screen flex flex-col items-center justify-center gap-3 dark:bg-black">
            <div className="text-3xl">403</div>
            <div className="text-gray-500">无权限访问该页面</div>
            <Link href="/" className="text-blue-500 underline">返回首页</Link>
        </div>
    );
}
