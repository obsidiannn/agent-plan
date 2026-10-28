// An highlighted block
'use client'
import { useState, useEffect, useLayoutEffect } from 'react';

export const useWindowSize = () => {
    const [windowSize, setWindowSize] = useState({
        width: 0,
        height: 1,
    });

    // 第二步：通过生命周期 Hook 声明回调的绑定和解绑逻辑
    useEffect(() => {
        const updateSize = () => {
            setWindowSize({
                width: window.innerWidth,
                height: window.innerHeight,
            })
        }
        if (window) {
            updateSize()
        }
        window.addEventListener('resize', updateSize);
        return () => window.removeEventListener('resize', updateSize);
    }, []);

    return windowSize;
}

export default {
    useWindowSize
}