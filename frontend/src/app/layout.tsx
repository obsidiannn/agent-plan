'use client'
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import ReactQueryProvider from "./providers/ReactQueryProvider";
import { AuthProvider } from "./providers/AuthProvider";
import ChakraProvider from '@/app/components/ChakraProvider'

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});



export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ChakraProvider>
          <ReactQueryProvider>
            <AuthProvider>
              {children}
            </AuthProvider>
          </ReactQueryProvider>
        </ChakraProvider>
      </body>
    </html>
  );
}
