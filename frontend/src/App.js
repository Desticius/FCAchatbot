import React, { useState, useRef, useEffect } from 'react';
import { Upload, Send, FileText, MessageCircle, AlertCircle, CheckCircle, Loader2, Bot, User, RefreshCw } from 'lucide-react';

const FCAHandbookChat = () => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [systemStatus, setSystemStatus] = useState('loading');
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [internalDocsLoaded, setInternalDocsLoaded] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  // temp localhost for development
  const API_BASE_URL = 'https://fcachatbot-353782424888.europe-west1.run.app';

  useEffect(() => {
    initializeSystem();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const initializeSystem = async () => {
    setSystemStatus('loading');
    
    // Add initial welcome message
    setMessages([{
      id: 1,
      type: 'system',
      content: '🏛️ FCA Regulations Chatbot! Initializing system and loading documents...',
      timestamp: new Date()
    }]);
  
    try {
      // First, just check health with better error handling
      console.log('Checking backend health...');
      
      const healthResponse = await fetch(`${API_BASE_URL}/health`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
        mode: 'cors',
      });
  
      if (!healthResponse.ok) {
        throw new Error(`Health check failed: ${healthResponse.status} ${healthResponse.statusText}`);
      }
  
      const healthData = await healthResponse.json();
      console.log('Health data received:', healthData);
  
      // Check if system is already ready
      if (healthData.internal_docs_loaded && healthData.vectorstore_initialized) {
        setSystemStatus('ready');
        setInternalDocsLoaded(true);
        setUploadedFiles(healthData.processed_files || []);
        
        setMessages(prev => [...prev, {
          id: Date.now(),
          type: 'system',
          content: `✅ System ready! Loaded ${healthData.processed_files?.length || 0} internal documents: ${healthData.processed_files?.join(', ') || 'None'}. You can now ask questions about FCA regulations!`,
          timestamp: new Date()
        }]);
        return;
      }
  
      // If not ready, check for internal documents separately
      console.log('Checking internal documents status...');
      
      const internalDocsResponse = await fetch(`${API_BASE_URL}/internal-documents-status`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
        mode: 'cors',
      });
  
      if (!internalDocsResponse.ok) {
        throw new Error(`Internal docs check failed: ${internalDocsResponse.status} ${internalDocsResponse.statusText}`);
      }
  
      const internalDocsData = await internalDocsResponse.json();
      console.log('Internal docs data:', internalDocsData);
  
      if (internalDocsData.total_files > 0) {
        // Internal documents exist but need to be loaded
        setMessages(prev => [...prev, {
          id: Date.now(),
          type: 'system',
          content: `📁 Found ${internalDocsData.total_files} internal documents: ${internalDocsData.pdf_files_found.join(', ')}. Loading them now...`,
          timestamp: new Date()
        }]);
        
        await loadInternalDocuments();
      } else {
        // No internal documents found
        setSystemStatus('no_docs');
        setMessages(prev => [...prev, {
          id: Date.now(),
          type: 'system',
          content: '📂 No internal documents found. Please upload a PDF to get started, or contact Benstrong290@gmail.com to add documents to the internal_documents directory.',
          timestamp: new Date()
        }]);
      }
  
    } catch (error) {
      console.error('Detailed initialization error:', error);
      setSystemStatus('error');
      
      // More specific error messages
      let errorMessage = '❌ Error initializing system: ';
      
      if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
        errorMessage += 'Network connection failed. Please check your internet connection and try again.';
      } else if (error.message.includes('CORS')) {
        errorMessage += 'Cross-origin request blocked. Please contact support.';
      } else if (error.message.includes('timeout')) {
        errorMessage += 'Request timed out. The server may be starting up, please try again in a moment.';
      } else {
        errorMessage += error.message;
      }
      
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'error',
        content: errorMessage + '\n\nTry refreshing the page or upload a PDF to continue.',
        timestamp: new Date()
      }]);
    }
  };

  const loadInternalDocuments = async () => {
    try {
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'system',
        content: '⏳ Loading internal documents, this may take a moment...',
        timestamp: new Date()
      }]);
  
      const response = await fetch(`${API_BASE_URL}/initialize-default`, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
        mode: 'cors',
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `Server error: ${response.status}`);
      }
      
      const data = await response.json();
      
      setSystemStatus('ready');
      setInternalDocsLoaded(true);
      setUploadedFiles(data.documents || [data.filename]);
      
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'system',
        content: `✅ Successfully loaded internal documents: ${(data.documents || [data.filename]).join(', ')}. System is now ready for questions!`,
        timestamp: new Date()
      }]);
  
    } catch (error) {
      console.error('Error loading internal documents:', error);
      setSystemStatus('no_docs');
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'system',
        content: `⚠️ Could not load internal documents: ${error.message}. You can still upload your own PDFs to get started.`,
        timestamp: new Date()
      }]);
    }
  };

  const reloadInternalDocuments = async () => {
    setIsReloading(true);
    
    try {
      const response = await fetch(`${API_BASE_URL}/reload-internal-documents`, {
        method: 'POST',
      });
      
      const data = await response.json();
      
      if (response.ok) {
        setSystemStatus('ready');
        setInternalDocsLoaded(true);
        setUploadedFiles(data.documents_loaded || []);
        
        setMessages(prev => [...prev, {
          id: Date.now(),
          type: 'system',
          content: `🔄 Successfully reloaded ${data.total_documents} internal documents: ${data.documents_loaded.join(', ')}`,
          timestamp: new Date()
        }]);
      } else {
        throw new Error(data.detail || 'Failed to reload internal documents');
      }
    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'error',
        content: `❌ Error reloading documents: ${error.message}`,
        timestamp: new Date()
      }]);
    } finally {
      setIsReloading(false);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'error',
        content: '❌ Please upload a PDF file only.',
        timestamp: new Date()
      }]);
      return;
    }

    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE_URL}/upload-pdf`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      
      if (response.ok) {
        setSystemStatus('ready');
        setUploadedFiles(data.all_documents || []);
        setMessages(prev => [...prev, {
          id: Date.now(),
          type: 'system',
          content: `✅ Successfully uploaded "${file.name}". This document has been added to the knowledge base${internalDocsLoaded ? ' alongside the internal documents' : ''}. Total documents: ${data.total_documents}`,
          timestamp: new Date()
        }]);
      } else {
        throw new Error(data.detail || 'Upload failed');
      }
    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'error',
        content: `❌ Error uploading file: ${error.message}`,
        timestamp: new Date()
      }]);
    } finally {
      setIsUploading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;
    
    if (systemStatus !== 'ready') {
      setMessages(prev => [...prev, {
        id: Date.now(),
        type: 'error',
        content: '⚠️ System not ready. Please wait for documents to load or upload a document to get started.',
        timestamp: new Date()
      }]);
      return;
    }

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputMessage,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: inputMessage }),
      });

      const data = await response.json();

      if (response.ok) {
        const botMessage = {
          id: Date.now() + 1,
          type: 'bot',
          content: data.answer,
          sources: data.source_documents || [],
          timestamp: new Date()
        };
        setMessages(prev => [...prev, botMessage]);
      } else {
        throw new Error(data.detail || 'Query failed');
      }
    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'error',
        content: `❌ Error: ${error.message}`,
        timestamp: new Date()
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const getStatusColor = () => {
    switch (systemStatus) {
      case 'ready': return 'text-green-500';
      case 'loading': return 'text-yellow-500';
      case 'no_docs': return 'text-orange-500';
      case 'error': return 'text-red-500';
      default: return 'text-gray-500';
    }
  };

  const getStatusText = () => {
    switch (systemStatus) {
      case 'ready': return `Ready (${uploadedFiles.length} docs)`;
      case 'loading': return 'Loading Documents...';
      case 'no_docs': return 'No Documents - Upload Required';
      case 'error': return 'Connection Error';
      default: return 'Initializing...';
    }
  };

  const MessageBubble = ({ message }) => {
    const isUser = message.type === 'user';
    const isSystem = message.type === 'system';
    const isError = message.type === 'error';

    return (
      <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-6`}>
        <div className={`flex max-w-4xl ${isUser ? 'flex-row-reverse' : 'flex-row'} items-start space-x-3`}>
          {/* Avatar */}
          <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
            isUser 
              ? 'bg-blue-500' 
              : isSystem || isError
                ? 'bg-gray-500'
                : 'bg-indigo-500'
          }`}>
            {isUser ? (
              <User className="w-5 h-5 text-white" />
            ) : isSystem || isError ? (
              <AlertCircle className="w-5 h-5 text-white" />
            ) : (
              <Bot className="w-5 h-5 text-white" />
            )}
          </div>

          {/* Message Content */}
          <div className={`px-6 py-4 rounded-2xl shadow-sm ${
            isUser 
              ? 'bg-blue-500 text-white ml-3' 
              : isSystem 
                ? 'bg-blue-50 text-blue-900 border-l-4 border-blue-500 mr-3' 
                : isError
                  ? 'bg-red-50 text-red-900 border-l-4 border-red-500 mr-3'
                  : 'bg-gray-50 text-gray-800 mr-3'
          }`}>
            {!isUser && (
              <div className="flex items-center mb-2">
                <span className="text-sm font-semibold">
                  {isSystem ? 'System' : isError ? 'Error' : 'FCA Assistant'}
                </span>
                <span className="text-xs opacity-70 ml-2">
                  {message.timestamp.toLocaleTimeString()}
                </span>
              </div>
            )}
            
            <div className="whitespace-pre-wrap leading-relaxed">{message.content}</div>
            
            {message.sources && message.sources.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-200">
                <div className="text-sm font-semibold mb-3 text-gray-700">📄 Source References:</div>
                <div className="space-y-3">
                  {message.sources.map((source, index) => (
                    <div key={index} className="bg-white p-3 rounded-lg border-l-4 border-indigo-400">
                      <div className="font-medium text-indigo-700 text-sm">
                        {source.metadata?.source_file && (
                          <span className="bg-indigo-100 px-2 py-1 rounded text-xs mr-2">
                            {source.metadata.source_file}
                          </span>
                        )}
                        Page {source.metadata?.page || 'Unknown'}
                      </div>
                      <div className="text-gray-600 text-sm mt-1 italic">
                        "{source.content}"
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <FileText className="w-8 h-8 text-blue-600 mr-3" />
              <div>
                <h1 className="text-2xl font-bold text-gray-900">FCA Regulations Chatbot</h1>
                <p className="text-sm text-gray-600">Ask questions about FCA regulations - internal documents loaded automatically</p>
              </div>
            </div>
            <div className="flex items-center space-x-6">
              {/* Status Indicator */}
              <div className="flex items-center">
                <div className={`w-3 h-3 rounded-full mr-2 ${
                  systemStatus === 'ready' ? 'bg-green-500' : 
                  systemStatus === 'error' ? 'bg-red-500' : 
                  systemStatus === 'no_docs' ? 'bg-orange-500' : 'bg-yellow-500'
                }`}></div>
                <span className={`text-sm font-medium ${getStatusColor()}`}>
                  {getStatusText()}
                </span>
              </div>

              {/* Reload Internal Documents Button */}
              {internalDocsLoaded && (
                <button
                  onClick={reloadInternalDocuments}
                  disabled={isReloading}
                  className="flex items-center px-3 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors shadow-sm text-sm"
                >
                  {isReloading ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <RefreshCw className="w-4 h-4 mr-2" />
                  )}
                  {isReloading ? 'Reloading...' : 'Reload Docs'}
                </button>
              )}
              
              {/* Upload Button */}
              <div className="flex items-center space-x-2">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  accept=".pdf"
                  className="hidden"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading}
                  className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                >
                  {isUploading ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Upload className="w-4 h-4 mr-2" />
                  )}
                  {isUploading ? 'Processing...' : 'Upload Additional PDF'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-6xl mx-auto p-6">
        {/* Messages Container */}
        <div className="bg-white rounded-xl shadow-sm mb-6 min-h-96">
          <div className="p-6">
            {messages.length === 0 ? (
              <div className="text-center py-12">
                <FileText className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">Welcome to FCA Assistant</h3>
                <p className="text-gray-500">Initializing system and loading internal documents...</p>
              </div>
            ) : (
              <div className="space-y-1">
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} />
                ))}
                {isLoading && (
                  <div className="flex justify-start mb-6">
                    <div className="flex items-center bg-gray-100 px-6 py-4 rounded-2xl">
                      <Loader2 className="w-5 h-5 mr-3 animate-spin text-blue-600" />
                      <span className="text-gray-600">Analyzing documents and generating response...</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
        </div>

        {/* Input Area */}
        <div className="bg-white rounded-xl shadow-sm border">
          <div className="p-6">
            <div className="flex items-end space-x-4">
              <div className="flex-1">
                <textarea
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder={systemStatus === 'ready' 
                    ? "Ask me about FCA regulations, compliance requirements, or your uploaded documents..." 
                    : systemStatus === 'loading'
                      ? "Loading documents, please wait..."
                      : "Upload a PDF or wait for internal documents to load..."
                  }
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none transition-all"
                  rows="3"
                  disabled={systemStatus !== 'ready'}
                />
              </div>
              <button
                onClick={handleSendMessage}
                disabled={isLoading || !inputMessage.trim() || systemStatus !== 'ready'}
                className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
            
            {uploadedFiles.length > 0 && (
              <div className="mt-3 flex items-center text-sm text-gray-600">
                <FileText className="w-4 h-4 mr-2" />
                <span>
                  Documents loaded: {uploadedFiles.join(', ')}
                  {internalDocsLoaded && ' (includes internal documents)'}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FCAHandbookChat;