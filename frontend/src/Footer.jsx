function IconGitHub(props) {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" {...props}>
      <path d="M12 2C6.48 2 2 6.58 2 12.19c0 4.49 2.87 8.3 6.84 9.64.5.1.68-.22.68-.49 0-.24-.01-1.04-.01-1.89-2.78.62-3.37-1.2-3.37-1.2-.45-1.18-1.11-1.5-1.11-1.5-.9-.63.07-.62.07-.62 1 .07 1.53 1.05 1.53 1.05.9 1.56 2.34 1.11 2.91.85.09-.66.35-1.11.64-1.37-2.22-.26-4.56-1.14-4.56-5.06 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05a9.32 9.32 0 0 1 5 0c1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.93-2.34 4.79-4.57 5.05.36.32.68.95.68 1.92 0 1.39-.01 2.51-.01 2.85 0 .27.18.6.69.49A10.02 10.02 0 0 0 22 12.19C22 6.58 17.52 2 12 2z" />
    </svg>
  );
}

export default function Footer({ repoUrl, profileUrl }) {
  return (
    <div className="footer-hover-zone">
      <footer className="footer">
        <span>
          Made by{" "}
          <a href={profileUrl} target="_blank" rel="noopener noreferrer">Kritika</a>
          {" "}—{" "}
          <a href={repoUrl} target="_blank" rel="noopener noreferrer">Suggest edits on GitHub</a>
        </span>
        <a className="footer-github-btn" href={repoUrl} target="_blank" rel="noopener noreferrer">
          <IconGitHub /> GitHub
        </a>
      </footer>
    </div>
  );
}
