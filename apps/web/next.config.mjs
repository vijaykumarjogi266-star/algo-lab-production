/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'http://127.0.0.1:8000/api/v1/:path*',
      },
      {
        source: '/api/dashboard/:path*',
        destination: 'http://127.0.0.1:8000/api/dashboard/:path*',
      },
    ];
  },
};

export default nextConfig;
