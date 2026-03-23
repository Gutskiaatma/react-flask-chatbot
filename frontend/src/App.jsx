import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './ChatApp.css';
import ReactMarkdown from 'react-markdown'; // ADD THIS


const App = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sessions, setSessions] = useState([]);
  const [session, setSession] = useState('Session 1');
  const [isTyping, setIsTyping] = useState(false);
  const bottomRef = useRef(null);
  const stopFlag = useRef(false); // ⛔ Stop flag

  useEffect(() => {
    axios.get('/sessions').then(res => {
      setSessions(res.data.sessions);
      if (res.data.sessions.length > 0 && !res.data.sessions.includes(session)) {
        setSession(res.data.sessions[0]);
      }
    });
  }, []);

  useEffect(() => {
    axios.get(`/history/${session}`).then(res => {
      setMessages(res.data.history);
    });
  }, [session]);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  function formatBotText(rawText) {
    return rawText
      .replace(/([.?!])\s*/g, '$1\n\n')
      .replace(/,\s*/g, ', ')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  async function generateAnswer(text) {
    const response = await axios.post('/ask', { text, session });
    return response.data.reply;
  }

  const sendMessage = async () => {
    if (!input.trim() || isTyping) return;

    const userMessage = { sender: 'user', text: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);
    stopFlag.current = false;

    try {
      const rawAnswer = await generateAnswer(input);
      const answer = formatBotText(rawAnswer);
      let botMessage = { sender: 'bot', text: '' };
      setMessages(prev => [...prev, botMessage]);

      for (let i = 0; i < answer.length; i++) {
        if (stopFlag.current) break;

        const char = answer[i];
        botMessage.text += char;

        setMessages(prev => {
          const newMessages = [...prev];
          newMessages[newMessages.length - 1] = { ...botMessage };
          return newMessages;
        });

        await new Promise(res => setTimeout(res, 5)); // Uniform fast delay

      }
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { sender: 'bot', text: 'Error getting response from AI.' }]);
    } finally {
      setIsTyping(false);
    }
  };

  const stopTyping = () => {
    stopFlag.current = true;
    setIsTyping(false);
  };

  const newSession = () => {
  const sessionNumbers = sessions
    .filter(s => s.startsWith("Session"))
    .map(s => parseInt(s.split(" ")[1]))
    .filter(n => !isNaN(n));

  const maxSession = sessionNumbers.length > 0 ? Math.max(...sessionNumbers) : 1;
  const newName = `Session ${maxSession + 1}`;

  setSessions(prev => [...prev, newName]);
  setSession(newName);
  setMessages([]);
};


  return (
    <div className="chat-container">
      <div className="sidebar">
        <h3>Chats</h3>
        <ul>
          {sessions.map((s, i) => (
            <li
              key={i}
              onClick={() => setSession(s)}
              className={s === session ? 'active' : ''}
            >
              {s}
            </li>
          ))}
        </ul>
        <button onClick={newSession}>+ New Chat</button>
      </div>

      <div className="chat-wrapper">
        <header className="chat-header">EchoNote</header>

        <main className="chat-body">
          {messages.map((msg, i) => (
  <div
    key={i}
    className={`message ${msg.sender === 'user' ? 'user-msg' : 'bot-msg'}`}
  >
    {msg.sender === 'bot' ? (
      <ReactMarkdown>{msg.text}</ReactMarkdown>
    ) : (
      <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{msg.text}</pre>
    )}
  </div>
))}

          <div ref={bottomRef} />
        </main>

        <footer className="chat-footer">
          <input
            type="text"
            placeholder="Type a message"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          />
          <button onClick={sendMessage}>&gt;</button>
          {isTyping && (
            <button onClick={stopTyping} className="stop-button">Stop</button>
          )}
        </footer>
      </div>
    </div>
  );
};

export default App;
