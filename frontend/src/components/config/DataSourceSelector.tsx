import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getDataSources, type DataSource } from '../../services/api';
import { CircleStackIcon, DocumentTextIcon, PlusIcon, MagnifyingGlassIcon } from '@heroicons/react/24/outline';
import { CheckCircleIcon } from '@heroicons/react/24/solid';

interface DataSourceSelectorProps {
    selectedId: string | null;
    onSelect: (dataSource: DataSource) => void;
    filterType?: 'database' | 'file' | null;
}

const DataSourceSelector: React.FC<DataSourceSelectorProps> = ({
    selectedId,
    onSelect,
    filterType = null,
}) => {
    const [dataSources, setDataSources] = useState<DataSource[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [typeFilter, setTypeFilter] = useState<'all' | 'database' | 'file'>(filterType || 'all');

    useEffect(() => {
        loadDataSources();
    }, []);

    const loadDataSources = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await getDataSources();
            setDataSources(response.data_sources || []);
        } catch (err) {
            console.error('Failed to load data sources:', err);
            setError('Failed to load data sources. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const filteredSources = dataSources.filter(ds => {
        const matchesType = typeFilter === 'all' || ds.source_type === typeFilter;
        const matchesSearch = !searchQuery || 
            ds.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
            (ds.description?.toLowerCase().includes(searchQuery.toLowerCase()));
        return matchesType && matchesSearch;
    });

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric'
        });
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                <span className="ml-2 text-gray-500 text-sm">Loading...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="text-center py-6">
                <p className="text-red-600 text-sm mb-2">{error}</p>
                <button onClick={loadDataSources} className="text-blue-600 hover:text-blue-700 text-sm font-medium">
                    Try Again
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-3">
            {/* Search and Filter Bar */}
            <div className="flex gap-2">
                {/* Search */}
                <div className="relative flex-1">
                    <MagnifyingGlassIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                        type="text"
                        placeholder="Search..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-md focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                    />
                </div>

                {/* Type Filter */}
                {!filterType && (
                    <select
                        value={typeFilter}
                        onChange={(e) => setTypeFilter(e.target.value as 'all' | 'database' | 'file')}
                        className="px-2 py-1.5 text-sm border border-gray-200 rounded-md focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                    >
                        <option value="all">All Types</option>
                        <option value="database">Databases</option>
                        <option value="file">Files</option>
                    </select>
                )}
            </div>

            {/* Data Sources List */}
            <div className="border border-gray-200 rounded-lg overflow-hidden divide-y divide-gray-100 max-h-64 overflow-y-auto">
                {filteredSources.length === 0 ? (
                    <div className="py-8 text-center">
                        <CircleStackIcon className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                        <p className="text-gray-500 text-sm mb-3">
                            {searchQuery || typeFilter !== 'all' ? 'No matching data sources' : 'No data sources yet'}
                        </p>
                        <Link
                            to="/data-sources"
                            className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 font-medium"
                        >
                            <PlusIcon className="w-4 h-4" />
                            Add Data Source
                        </Link>
                    </div>
                ) : (
                    filteredSources.map((ds) => {
                        const isSelected = selectedId === ds.id;
                        return (
                            <button
                                key={ds.id}
                                onClick={() => onSelect(ds)}
                                className={`w-full flex items-start gap-3 px-3 py-3 text-left transition-colors hover:bg-gray-50 ${
                                    isSelected ? 'bg-blue-50 hover:bg-blue-50' : ''
                                }`}
                            >
                                {/* Selection indicator */}
                                <div className="flex-shrink-0 pt-0.5">
                                    {isSelected ? (
                                        <CheckCircleIcon className="w-5 h-5 text-blue-600" />
                                    ) : (
                                        <div className="w-5 h-5 rounded-full border-2 border-gray-300" />
                                    )}
                                </div>

                                {/* Icon */}
                                <div className={`flex-shrink-0 w-9 h-9 rounded-md flex items-center justify-center ${
                                    ds.source_type === 'database' ? 'bg-blue-100' : 'bg-green-100'
                                }`}>
                                    {ds.source_type === 'database' 
                                        ? <CircleStackIcon className="w-5 h-5 text-blue-600" />
                                        : <DocumentTextIcon className="w-5 h-5 text-green-600" />
                                    }
                                </div>

                                {/* Content */}
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-0.5">
                                        <span className="font-medium text-gray-900 text-sm">
                                            {ds.title}
                                        </span>
                                        <span className={`flex-shrink-0 px-1.5 py-0.5 text-xs rounded ${
                                            ds.source_type === 'database'
                                                ? 'bg-blue-100 text-blue-700'
                                                : 'bg-green-100 text-green-700'
                                        }`}>
                                            {ds.source_type === 'database' 
                                                ? (ds.db_engine_type || 'DB')
                                                : (ds.file_type?.toUpperCase() || 'File')
                                            }
                                        </span>
                                        {ds.row_count !== undefined && ds.row_count !== null && (
                                            <span className="text-xs text-gray-400">
                                                {ds.row_count.toLocaleString()} rows
                                            </span>
                                        )}
                                    </div>
                                    {ds.description && (
                                        <p className="text-xs text-gray-500 line-clamp-2">
                                            {ds.description}
                                        </p>
                                    )}
                                </div>

                                {/* Created date */}
                                <div className="flex-shrink-0 text-right">
                                    <span className="text-xs text-gray-400">
                                        {formatDate(ds.created_at)}
                                    </span>
                                </div>
                            </button>
                        );
                    })
                )}
            </div>

            {/* Add New Link */}
            {filteredSources.length > 0 && (
                <div className="text-center">
                    <Link
                        to="/data-sources"
                        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-blue-600"
                    >
                        <PlusIcon className="w-4 h-4" />
                        Add new data source
                    </Link>
                </div>
            )}
        </div>
    );
};

export default DataSourceSelector;
