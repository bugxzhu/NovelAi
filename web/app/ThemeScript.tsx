// Inline script to set theme class before React hydrates — prevents flash.
// Reads the persisted theme from localStorage; defaults to dark on any error.
export function ThemeScript() {
  const code = `(function(){try{var s=JSON.parse(localStorage.getItem('m2b-ui')||'{}');var t=(s.state&&s.state.theme)||'dark';if(t==='dark'){document.documentElement.classList.add('dark');}}catch(e){document.documentElement.classList.add('dark');}})();`;
  return <script dangerouslySetInnerHTML={{ __html: code }} />;
}
