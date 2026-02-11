"""
XYS Sign Scripts - 完整逆向实现

纯签名模式：直接调用 mnsv2 + 自定义编码生成签名，不发送任何请求。

逆向发现：
1. XYS 使用自定义 Base64 字符表
2. Af 函数将字符串转为 UTF-8 字节数组
3. TF 函数使用自定义字符表进行 Base64 编码
"""

# Stealth script for anti-detection
STEALTH_SCRIPT = """
(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
    window.chrome = { runtime: {} };
})();
"""

# Script to check if page loaded correctly
PAGE_CHECK_SCRIPT = """
() => {
    const body = document.body;
    if (!body) return { success: false, error: 'No body element' };
    return { success: true, hasMnsv2: typeof window.mnsv2 === 'function' };
}
"""

# XYS 拦截器 - 捕获 X-S-Common
XYS_INTERCEPTOR_SCRIPT = """
(() => {
    window.__xsCommon = '';
    window.__xysInterceptorReady = true;

    const originalXHRSetHeader = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
        if (name === 'X-S-Common' || name === 'x-s-common') {
            window.__xsCommon = value;
        }
        return originalXHRSetHeader.apply(this, arguments);
    };
})();
"""

# 检查拦截器是否就绪
CHECK_INTERCEPTOR_READY_SCRIPT = """
() => {
    return window.__xysInterceptorReady === true;
}
"""

# 检查 mnsv2 是否可用
CHECK_MNSV2_SCRIPT = """
() => {
    return typeof window.mnsv2 === 'function';
}
"""

# 获取 X-S-Common
GET_XS_COMMON_SCRIPT = """
() => {
    return window.__xsCommon || '';
}
"""

# 清空签名存储
CLEAR_SIGNATURE_STORE_SCRIPT = """
() => {
    return { cleared: true };
}
"""

# 纯签名生成脚本 - 完整逆向实现
GENERATE_XYS_SIGNATURE_SCRIPT = """
(args) => {
    try {
        const url = args[0] || '';
        const data = args[1] || '';

        // 检查 mnsv2 是否可用
        if (typeof window.mnsv2 !== 'function') {
            return { success: false, error: 'mnsv2 function not available' };
        }

        // ========== XYS 自定义 Base64 字符表 ==========
        const XHS_CHAR_TABLE = "ZmserbBoHQtNP+wOcza/LpngG8yJq42KWYj0DSfdikx3VT16IlUAFM97hECvuRX5";
        const charTable = XHS_CHAR_TABLE.split('');

        // ========== MD5 实现 ==========
        const md5 = (function() {
            function safeAdd(x, y) {
                var lsw = (x & 0xFFFF) + (y & 0xFFFF);
                var msw = (x >> 16) + (y >> 16) + (lsw >> 16);
                return (msw << 16) | (lsw & 0xFFFF);
            }
            function bitRotateLeft(num, cnt) {
                return (num << cnt) | (num >>> (32 - cnt));
            }
            function md5cmn(q, a, b, x, s, t) {
                return safeAdd(bitRotateLeft(safeAdd(safeAdd(a, q), safeAdd(x, t)), s), b);
            }
            function md5ff(a, b, c, d, x, s, t) {
                return md5cmn((b & c) | ((~b) & d), a, b, x, s, t);
            }
            function md5gg(a, b, c, d, x, s, t) {
                return md5cmn((b & d) | (c & (~d)), a, b, x, s, t);
            }
            function md5hh(a, b, c, d, x, s, t) {
                return md5cmn(b ^ c ^ d, a, b, x, s, t);
            }
            function md5ii(a, b, c, d, x, s, t) {
                return md5cmn(c ^ (b | (~d)), a, b, x, s, t);
            }
            function binlMD5(x, len) {
                x[len >> 5] |= 0x80 << (len % 32);
                x[(((len + 64) >>> 9) << 4) + 14] = len;
                var a = 1732584193, b = -271733879, c = -1732584194, d = 271733878;
                for (var i = 0; i < x.length; i += 16) {
                    var olda = a, oldb = b, oldc = c, oldd = d;
                    a = md5ff(a, b, c, d, x[i], 7, -680876936);
                    d = md5ff(d, a, b, c, x[i + 1], 12, -389564586);
                    c = md5ff(c, d, a, b, x[i + 2], 17, 606105819);
                    b = md5ff(b, c, d, a, x[i + 3], 22, -1044525330);
                    a = md5ff(a, b, c, d, x[i + 4], 7, -176418897);
                    d = md5ff(d, a, b, c, x[i + 5], 12, 1200080426);
                    c = md5ff(c, d, a, b, x[i + 6], 17, -1473231341);
                    b = md5ff(b, c, d, a, x[i + 7], 22, -45705983);
                    a = md5ff(a, b, c, d, x[i + 8], 7, 1770035416);
                    d = md5ff(d, a, b, c, x[i + 9], 12, -1958414417);
                    c = md5ff(c, d, a, b, x[i + 10], 17, -42063);
                    b = md5ff(b, c, d, a, x[i + 11], 22, -1990404162);
                    a = md5ff(a, b, c, d, x[i + 12], 7, 1804603682);
                    d = md5ff(d, a, b, c, x[i + 13], 12, -40341101);
                    c = md5ff(c, d, a, b, x[i + 14], 17, -1502002290);
                    b = md5ff(b, c, d, a, x[i + 15], 22, 1236535329);
                    a = md5gg(a, b, c, d, x[i + 1], 5, -165796510);
                    d = md5gg(d, a, b, c, x[i + 6], 9, -1069501632);
                    c = md5gg(c, d, a, b, x[i + 11], 14, 643717713);
                    b = md5gg(b, c, d, a, x[i], 20, -373897302);
                    a = md5gg(a, b, c, d, x[i + 5], 5, -701558691);
                    d = md5gg(d, a, b, c, x[i + 10], 9, 38016083);
                    c = md5gg(c, d, a, b, x[i + 15], 14, -660478335);
                    b = md5gg(b, c, d, a, x[i + 4], 20, -405537848);
                    a = md5gg(a, b, c, d, x[i + 9], 5, 568446438);
                    d = md5gg(d, a, b, c, x[i + 14], 9, -1019803690);
                    c = md5gg(c, d, a, b, x[i + 3], 14, -187363961);
                    b = md5gg(b, c, d, a, x[i + 8], 20, 1163531501);
                    a = md5gg(a, b, c, d, x[i + 13], 5, -1444681467);
                    d = md5gg(d, a, b, c, x[i + 2], 9, -51403784);
                    c = md5gg(c, d, a, b, x[i + 7], 14, 1735328473);
                    b = md5gg(b, c, d, a, x[i + 12], 20, -1926607734);
                    a = md5hh(a, b, c, d, x[i + 5], 4, -378558);
                    d = md5hh(d, a, b, c, x[i + 8], 11, -2022574463);
                    c = md5hh(c, d, a, b, x[i + 11], 16, 1839030562);
                    b = md5hh(b, c, d, a, x[i + 14], 23, -35309556);
                    a = md5hh(a, b, c, d, x[i + 1], 4, -1530992060);
                    d = md5hh(d, a, b, c, x[i + 4], 11, 1272893353);
                    c = md5hh(c, d, a, b, x[i + 7], 16, -155497632);
                    b = md5hh(b, c, d, a, x[i + 10], 23, -1094730640);
                    a = md5hh(a, b, c, d, x[i + 13], 4, 681279174);
                    d = md5hh(d, a, b, c, x[i + 0], 11, -358537222);
                    c = md5hh(c, d, a, b, x[i + 3], 16, -722521979);
                    b = md5hh(b, c, d, a, x[i + 6], 23, 76029189);
                    a = md5hh(a, b, c, d, x[i + 9], 4, -640364487);
                    d = md5hh(d, a, b, c, x[i + 12], 11, -421815835);
                    c = md5hh(c, d, a, b, x[i + 15], 16, 530742520);
                    b = md5hh(b, c, d, a, x[i + 2], 23, -995338651);
                    a = md5ii(a, b, c, d, x[i], 6, -198630844);
                    d = md5ii(d, a, b, c, x[i + 7], 10, 1126891415);
                    c = md5ii(c, d, a, b, x[i + 14], 15, -1416354905);
                    b = md5ii(b, c, d, a, x[i + 5], 21, -57434055);
                    a = md5ii(a, b, c, d, x[i + 12], 6, 1700485571);
                    d = md5ii(d, a, b, c, x[i + 3], 10, -1894986606);
                    c = md5ii(c, d, a, b, x[i + 10], 15, -1051523);
                    b = md5ii(b, c, d, a, x[i + 1], 21, -2054922799);
                    a = md5ii(a, b, c, d, x[i + 8], 6, 1873313359);
                    d = md5ii(d, a, b, c, x[i + 15], 10, -30611744);
                    c = md5ii(c, d, a, b, x[i + 6], 15, -1560198380);
                    b = md5ii(b, c, d, a, x[i + 13], 21, 1309151649);
                    a = md5ii(a, b, c, d, x[i + 4], 6, -145523070);
                    d = md5ii(d, a, b, c, x[i + 11], 10, -1120210379);
                    c = md5ii(c, d, a, b, x[i + 2], 15, 718787259);
                    b = md5ii(b, c, d, a, x[i + 9], 21, -343485551);
                    a = safeAdd(a, olda);
                    b = safeAdd(b, oldb);
                    c = safeAdd(c, oldc);
                    d = safeAdd(d, oldd);
                }
                return [a, b, c, d];
            }
            function binl2hex(binarray) {
                var hexTab = '0123456789abcdef';
                var str = '';
                for (var i = 0; i < binarray.length * 4; i++) {
                    str += hexTab.charAt((binarray[i >> 2] >> ((i % 4) * 8 + 4)) & 0xF) +
                           hexTab.charAt((binarray[i >> 2] >> ((i % 4) * 8)) & 0xF);
                }
                return str;
            }
            function str2binl(str) {
                var bin = [];
                for (var i = 0; i < str.length * 8; i += 8) {
                    bin[i >> 5] |= (str.charCodeAt(i / 8) & 0xFF) << (i % 32);
                }
                return bin;
            }
            function utf8Encode(str) {
                return unescape(encodeURIComponent(str));
            }
            return function(str) {
                var utf8 = utf8Encode(str);
                return binl2hex(binlMD5(str2binl(utf8), utf8.length * 8));
            };
        })();

        // ========== Af 函数：UTF-8 编码 ==========
        function Af(str) {
            var encoded = encodeURIComponent(str);
            var bytes = [];
            for (var i = 0; i < encoded.length; i++) {
                var ch = encoded.charAt(i);
                if (ch === '%') {
                    var hex = parseInt(encoded.charAt(i + 1) + encoded.charAt(i + 2), 16);
                    bytes.push(hex);
                    i += 2;
                } else {
                    bytes.push(ch.charCodeAt(0));
                }
            }
            return bytes;
        }

        // ========== TF 函数：自定义 Base64 编码 ==========
        function b64Chunk(a) {
            return charTable[a >> 18 & 63] + charTable[a >> 12 & 63] + charTable[a >> 6 & 63] + charTable[63 & a];
        }

        function encodeChunk(bytes, start, end) {
            var result = [];
            for (var i = start; i < end; i += 3) {
                var chunk = (bytes[i] << 16 & 0xff0000) + (bytes[i + 1] << 8 & 65280) + (255 & bytes[i + 2]);
                result.push(b64Chunk(chunk));
            }
            return result.join('');
        }

        function TF(bytes) {
            var len = bytes.length;
            var remainder = len % 3;
            var result = [];
            var maxChunk = 16383;

            // 处理完整的 3 字节块
            var mainLen = len - remainder;
            for (var i = 0; i < mainLen; i += maxChunk) {
                var end = i + maxChunk > mainLen ? mainLen : i + maxChunk;
                result.push(encodeChunk(bytes, i, end));
            }

            // 处理剩余字节
            if (remainder === 1) {
                var tmp = bytes[len - 1];
                result.push(charTable[tmp >> 2] + charTable[tmp << 4 & 63] + '==');
            } else if (remainder === 2) {
                var tmp = (bytes[len - 2] << 8) + bytes[len - 1];
                result.push(charTable[tmp >> 10] + charTable[tmp >> 4 & 63] + charTable[tmp << 2 & 63] + '=');
            }

            return result.join('');
        }

        // ========== 构建签名 ==========
        // 1. 构建 payload
        const payload = url + data;

        // 2. 计算 MD5 hash
        const hash = md5(payload);

        // 3. 调用 mnsv2 生成核心签名
        const mnsResult = window.mnsv2(payload, hash);

        if (!mnsResult) {
            return { success: false, error: 'mnsv2 returned empty result' };
        }

        // 4. 构建签名对象
        const signObj = {
            x0: '4.2.8',
            x1: 'ugc',
            x2: window._webmsxyw_platform || 'Windows',
            x3: mnsResult,
            x4: data ? typeof data : ''
        };

        // 5. JSON 序列化 -> UTF-8 编码 -> 自定义 Base64
        const jsonStr = JSON.stringify(signObj);
        const bytes = Af(jsonStr);
        const encoded = TF(bytes);

        const timestamp = Date.now();

        return {
            success: true,
            'X-s': 'XYS_' + encoded,
            'X-t': timestamp.toString(),
            'X-s-common': window.__xsCommon || ''
        };

    } catch (error) {
        return { success: false, error: error.message };
    }
}
"""

# 备用：触发真实请求获取签名
TRIGGER_REAL_SIGNATURE_SCRIPT = """
async (args) => {
    try {
        const phone = args[0] || '13800138000';
        window.__capturedSignature = null;

        if (!window.__headerHooked) {
            const originalSetHeader = XMLHttpRequest.prototype.setRequestHeader;
            XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
                if (name === 'X-s' && value && value.startsWith('XYS_')) {
                    window.__capturedSignature = window.__capturedSignature || {};
                    window.__capturedSignature['X-s'] = value;
                }
                if (name === 'X-t') {
                    window.__capturedSignature = window.__capturedSignature || {};
                    window.__capturedSignature['X-t'] = value;
                }
                if (name === 'X-S-Common') {
                    window.__capturedSignature = window.__capturedSignature || {};
                    window.__capturedSignature['X-s-common'] = value;
                    window.__xsCommon = value;
                }
                return originalSetHeader.apply(this, arguments);
            };
            window.__headerHooked = true;
        }

        const phoneInput = document.querySelector('input[placeholder*="手机"]');
        if (phoneInput) {
            phoneInput.value = phone;
            phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
        }

        await new Promise(r => setTimeout(r, 300));

        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
            if (el.textContent?.trim() === '发送验证码' && el.offsetParent !== null) {
                el.click();
                break;
            }
        }

        await new Promise(r => setTimeout(r, 1500));

        if (window.__capturedSignature && window.__capturedSignature['X-s']) {
            return { success: true, ...window.__capturedSignature };
        }

        return { success: false, error: 'No signature captured' };
    } catch (error) {
        return { success: false, error: error.message };
    }
}
"""
