import React, { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, File, X } from 'lucide-react';

const FileUpload = ({ onUpload, acceptedFormats = ['.pdf'] }) => {
  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      onUpload(acceptedFiles[0]);
    }
  }, [onUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': acceptedFormats,
    },
    multiple: false,
  });

  return (
    <div
      {...getRootProps()}
      className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
        isDragActive
          ? 'border-primary bg-blue-50'
          : 'border-gray-300 hover:border-primary hover:bg-gray-50'
      }`}
    >
      <input {...getInputProps()} />
      <Upload className="w-12 h-12 mx-auto mb-4 text-gray-400" />
      {isDragActive ? (
        <p className="text-primary font-medium">Déposez le fichier ici...</p>
      ) : (
        <div>
          <p className="text-gray-700 font-medium mb-1">
            Glissez-déposez un PDF ici ou cliquez pour sélectionner
          </p>
          <p className="text-sm text-gray-500">Formats acceptés: PDF</p>
        </div>
      )}
    </div>
  );
};

export default FileUpload;

