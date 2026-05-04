import React from 'react';

export interface PaginationProps {
    /** Current page number (1-indexed) */
    page: number;
    /** Total number of pages */
    totalPages: number;
    /** Total number of items */
    totalItems: number;
    /** Number of items per page */
    pageSize: number;
    /** Callback when page changes */
    onPageChange: (page: number) => void;
    /** Whether pagination controls are disabled (e.g., during loading) */
    disabled?: boolean;
    /** Number of page buttons to show around current page */
    siblingCount?: number;
}

/**
 * Generate array of page numbers to display
 */
function getPageNumbers(
    currentPage: number,
    totalPages: number,
    siblingCount: number
): (number | 'ellipsis')[] {
    const pages: (number | 'ellipsis')[] = [];
    
    // Always show first page
    pages.push(1);
    
    // Calculate range around current page
    const leftSibling = Math.max(2, currentPage - siblingCount);
    const rightSibling = Math.min(totalPages - 1, currentPage + siblingCount);
    
    // Add left ellipsis if needed
    if (leftSibling > 2) {
        pages.push('ellipsis');
    }
    
    // Add pages around current page
    for (let i = leftSibling; i <= rightSibling; i++) {
        if (i !== 1 && i !== totalPages) {
            pages.push(i);
        }
    }
    
    // Add right ellipsis if needed
    if (rightSibling < totalPages - 1) {
        pages.push('ellipsis');
    }
    
    // Always show last page if more than 1 page
    if (totalPages > 1) {
        pages.push(totalPages);
    }
    
    return pages;
}

/**
 * Reusable pagination component with prev/next buttons and page numbers.
 * 
 * @example
 * <Pagination
 *   page={currentPage}
 *   totalPages={10}
 *   totalItems={100}
 *   pageSize={10}
 *   onPageChange={(page) => setCurrentPage(page)}
 * />
 */
const Pagination: React.FC<PaginationProps> = ({
    page,
    totalPages,
    totalItems,
    pageSize,
    onPageChange,
    disabled = false,
    siblingCount = 1,
}) => {
    // Don't render if only one page or no pages
    if (totalPages <= 1) {
        return null;
    }

    const pageNumbers = getPageNumbers(page, totalPages, siblingCount);
    
    // Calculate item range being displayed
    const startItem = (page - 1) * pageSize + 1;
    const endItem = Math.min(page * pageSize, totalItems);

    const handlePrevious = () => {
        if (page > 1 && !disabled) {
            onPageChange(page - 1);
        }
    };

    const handleNext = () => {
        if (page < totalPages && !disabled) {
            onPageChange(page + 1);
        }
    };

    const handlePageClick = (pageNum: number) => {
        if (pageNum !== page && !disabled) {
            onPageChange(pageNum);
        }
    };

    const baseButtonClass = "px-3 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1";
    const activeButtonClass = "bg-blue-600 text-white";
    const inactiveButtonClass = "text-gray-700 bg-white border border-gray-300 hover:bg-gray-50";
    const disabledButtonClass = "text-gray-400 bg-gray-100 border border-gray-200 cursor-not-allowed";

    return (
        <div className="flex items-center justify-between px-4 py-3 bg-white border-t border-gray-200 sm:px-6">
            {/* Mobile view */}
            <div className="flex justify-between flex-1 sm:hidden">
                <button
                    onClick={handlePrevious}
                    disabled={page === 1 || disabled}
                    className={`${baseButtonClass} ${page === 1 || disabled ? disabledButtonClass : inactiveButtonClass}`}
                >
                    Previous
                </button>
                <span className="flex items-center px-4 text-sm text-gray-700">
                    Page {page} of {totalPages}
                </span>
                <button
                    onClick={handleNext}
                    disabled={page === totalPages || disabled}
                    className={`${baseButtonClass} ${page === totalPages || disabled ? disabledButtonClass : inactiveButtonClass}`}
                >
                    Next
                </button>
            </div>

            {/* Desktop view */}
            <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
                <div>
                    <p className="text-sm text-gray-700">
                        Showing <span className="font-medium">{startItem}</span> to{' '}
                        <span className="font-medium">{endItem}</span> of{' '}
                        <span className="font-medium">{totalItems}</span> results
                    </p>
                </div>
                <div>
                    <nav className="inline-flex items-center gap-1" aria-label="Pagination">
                        {/* Previous button */}
                        <button
                            onClick={handlePrevious}
                            disabled={page === 1 || disabled}
                            className={`${baseButtonClass} ${page === 1 || disabled ? disabledButtonClass : inactiveButtonClass}`}
                            aria-label="Previous page"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                            </svg>
                        </button>

                        {/* Page numbers */}
                        {pageNumbers.map((pageNum, index) => (
                            pageNum === 'ellipsis' ? (
                                <span
                                    key={`ellipsis-${index}`}
                                    className="px-2 py-2 text-sm text-gray-500"
                                >
                                    ...
                                </span>
                            ) : (
                                <button
                                    key={pageNum}
                                    onClick={() => handlePageClick(pageNum)}
                                    disabled={disabled}
                                    className={`${baseButtonClass} min-w-[40px] ${
                                        pageNum === page
                                            ? activeButtonClass
                                            : disabled
                                            ? disabledButtonClass
                                            : inactiveButtonClass
                                    }`}
                                    aria-label={`Page ${pageNum}`}
                                    aria-current={pageNum === page ? 'page' : undefined}
                                >
                                    {pageNum}
                                </button>
                            )
                        ))}

                        {/* Next button */}
                        <button
                            onClick={handleNext}
                            disabled={page === totalPages || disabled}
                            className={`${baseButtonClass} ${page === totalPages || disabled ? disabledButtonClass : inactiveButtonClass}`}
                            aria-label="Next page"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                        </button>
                    </nav>
                </div>
            </div>
        </div>
    );
};

export default Pagination;
