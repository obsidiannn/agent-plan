import dayjs from 'dayjs'

const plusDateLabel = (date: string, days: number): string => {
    const dateObj = dayjs(date, 'YYYYMMDD');
    return dateObj.add(days, 'day').format('YYYYMMDD');
}

const convertHikyuuDateToLabel = (date: number): string => {
    // 202101110000
    const dateObj = dayjs(date + "", 'YYYYMMDDHHmm');
    return dateObj.format('YYYYMMDD');
}

export default {
    plusDateLabel,
    convertHikyuuDateToLabel
}