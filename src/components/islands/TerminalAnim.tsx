/**
 * TerminalAnim — React island with a typing animation showing
 * security-related commands. Uses framer-motion for cursor blink.
 */
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

const COMMANDS = [
  '$ nmap -sV -sC 10.10.11.42',
  '$ gobuster dir -u http://target -w /usr/share/wordlists/common.txt',
  '$ sqlmap -u "http://target/page?id=1" --batch',
  '$ hashcat -m 1800 hash.txt rockyou.txt',
  '$ python3 exploit.py --rhost 10.10.11.42 --lhost tun0',
];

export default function TerminalAnim() {
  const [lines, setLines] = useState<string[]>([]);
  const [currentLine, setCurrentLine] = useState('');
  const [cmdIndex, setCmdIndex] = useState(0);
  const [charIndex, setCharIndex] = useState(0);

  useEffect(() => {
    if (cmdIndex >= COMMANDS.length) {
      // Reset after all commands typed
      const timeout = setTimeout(() => {
        setLines([]);
        setCurrentLine('');
        setCmdIndex(0);
        setCharIndex(0);
      }, 3000);
      return () => clearTimeout(timeout);
    }

    const cmd = COMMANDS[cmdIndex];
    if (charIndex < cmd.length) {
      const timeout = setTimeout(() => {
        setCurrentLine(cmd.slice(0, charIndex + 1));
        setCharIndex(charIndex + 1);
      }, 40 + Math.random() * 30);
      return () => clearTimeout(timeout);
    } else {
      // Line complete, move to next
      const timeout = setTimeout(() => {
        setLines((prev) => [...prev, cmd]);
        setCurrentLine('');
        setCmdIndex(cmdIndex + 1);
        setCharIndex(0);
      }, 800);
      return () => clearTimeout(timeout);
    }
  }, [cmdIndex, charIndex]);

  return (
    <div className="terminal-anim">
      <div className="terminal-anim__header">
        <span className="terminal-anim__dot terminal-anim__dot--red" />
        <span className="terminal-anim__dot terminal-anim__dot--yellow" />
        <span className="terminal-anim__dot terminal-anim__dot--green" />
        <span className="terminal-anim__dot-title">xyvora@kali:~</span>
      </div>
      <div className="terminal-anim__body">
        {lines.map((line, i) => (
          <div key={i} className="terminal-anim__line">{line}</div>
        ))}
        {cmdIndex < COMMANDS.length && (
          <div className="terminal-anim__line">
            {currentLine}
            <motion.span
              className="terminal-anim__cursor"
              animate={{ opacity: [1, 0] }}
              transition={{ duration: 0.7, repeat: Infinity, repeatType: 'reverse' }}
            >
              █
            </motion.span>
          </div>
        )}
      </div>
    </div>
  );
}
