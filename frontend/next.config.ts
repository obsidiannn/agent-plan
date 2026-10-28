import type { NextConfig } from "next";
import nextBuildFilter, { FilterOptions } from "next-build-filter";

const filterConfig: FilterOptions = {
  enabled: true,
  verbose: true,
  enableInDev: true,
  supportPagesRouter: true,
  supportAppRouter: true,
  appDir: 'src/app',

}

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  turbopack: {},
  async rewrites() {
    const backend = process.env.PYTHON_BACKEND_URL || "http://localhost:8000";
    return {
      // beforeFiles 优先于 route handlers, 确保 /api/* 全部代理到 Python 后端
      beforeFiles: [
        {
          source: "/api/:path*",
          destination: `${backend}/api/:path*`,
        },
      ],
    };
  },
};

const filterNextConfig = nextBuildFilter(filterConfig)(nextConfig);
export default filterNextConfig;
