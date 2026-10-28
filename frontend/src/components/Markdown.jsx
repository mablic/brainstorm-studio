import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const components={
 table:({children})=><div className="markdown-table-scroll"><table>{children}</table></div>,
 a:({href,children})=><a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
};
export default function Markdown({children}){
 return <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{children}</ReactMarkdown>;
}
